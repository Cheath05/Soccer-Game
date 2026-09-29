"""On-ball decisions and their physical execution.

The player on the ball scores his options (shoot, pass to each teammate or into a runner's
path, cross, dribble, clear) by estimated success probability x value gained, minus the
cost of losing the ball where he stands, plus tactical and role biases. He then samples
one option (softmax), so better decision-makers choose well more consistently.

Execution is physical: the pass or shot leaves with an error that depends on the relevant
skill and pressure, and the ball then has to beat interceptors, blocks and the keeper.
"""

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from footsim.defs.positions import PositionGroup
from footsim.match.engine import duels
from footsim.match.engine.behaviours import offside_line
from footsim.match.engine.pitch import (
    GOAL_HALF,
    LENGTH,
    MID_Y,
    expected_goal,
    in_own_box,
    loss_cost,
    norm,
    norms,
    threat,
)
from footsim.match.engine.state import MAX_SUBS, PassInfo, ShotInfo
from footsim.match.penalties import penalty_probability
from footsim.match.ratings import match_rating

if TYPE_CHECKING:
    from footsim.match.engine.engine import MatchEngine

RETAIN = 0.015  # value of simply keeping the ball
CONTROL_RADIUS = 1.3
KEEPER_REACH = 2.4  # arms: keepers gather balls further away in their own box
KEEPER_DIVE = 2.5  # how far a keeper can throw himself to catch a shot
NO_OFFSIDE = frozenset({"throw_in", "goal_kick", "corner"})  # restarts (Law 11)
MIN_SHOT_XG = 0.05  # open play: nobody shoots from hopeless positions...
LONG_SHOT_XG = 0.02  # ...except from 18-30 m with room to shoot
HEADER_ON_GOAL_XG = 0.04  # a header this good goes for goal; otherwise it's knocked down


@dataclass(frozen=True)
class PassOption:
    receiver: int  # -1 for a clearance
    target: tuple[float, float]  # attacking frame
    lofted: bool
    estimate: float  # estimated success chance


@dataclass(frozen=True)
class CarryOption:
    target: tuple[float, float]  # attacking frame
    urgent: bool


Option = tuple[float, str, PassOption | CarryOption | None]


def _sigmoid(x: float | np.ndarray) -> float | np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


# --- possession ------------------------------------------------------------------------


def gain_possession(eng: "MatchEngine", i: int, delay: float | None = None,
                    how: str = "loose") -> None:
    """``how`` says how the ball was won (for the match log): pass, interception, recovery,
    tackle, loose, save, claim, or the restart kind."""
    if eng.last_touch < 0 or int(eng.team_of[eng.last_touch]) != int(eng.team_of[i]):
        eng.turnover_at = eng.t
    team = int(eng.team_of[i])
    if not eng.possessions or eng.possessions[-1].team != team:
        eng.start_possession(team, how)
    eng.owner = i
    eng.state = "owned"
    eng.ball_z = 0.0
    eng.ball_vz = 0.0
    eng.last_touch = i
    eng.pass_info = None
    eng.carry_target = None
    eng.carry_urgent = False
    if delay is None:
        hold = eng.effect(team, "tempo").hold
        if how in ("tackle", "interception", "recovery", "loose") and _counter_chance(eng, i):
            hold = eng.defs.tactics.transition.counter_hold  # win it and go
        delay = hold + 0.35 * (1 - eng.a(i, "first_touch") / 100) + float(eng.rng.uniform(0, 0.2))
    eng.decide_at = eng.t + delay


def _counter_chance(eng: "MatchEngine", i: int) -> bool:
    """Did ``i`` just win the ball in his own half with room to break into?"""
    team = int(eng.team_of[i])
    x, _ = eng.to_att(team, float(eng.pos[i, 0]), float(eng.pos[i, 1]))
    if x > LENGTH / 2:
        return False
    keeper = eng.keeper(1 - team)
    ahead = sum(1 for k in eng.team_indices(1 - team) if k != keeper
                and eng.to_att(team, float(eng.pos[k, 0]), float(eng.pos[k, 1]))[0] > x)
    return ahead <= 6


def owner_tick(eng: "MatchEngine") -> None:
    i = eng.owner
    if duels.contest(eng, i):
        return
    team = int(eng.team_of[i])
    opp = eng.team_indices(1 - team)
    pressed = len(opp) and float(np.min(norms(eng.pos[opp] - eng.pos[i], axis=1))) < 1.8
    if eng.t >= eng.decide_at or (pressed and eng.t >= eng.decide_at - 0.25):
        decide(eng, i)


# --- decisions -------------------------------------------------------------------------


def decide(eng: "MatchEngine", i: int, mode: str | None = None) -> None:
    """Choose and start the owner's next action. ``mode`` restricts options at restarts."""
    team = int(eng.team_of[i])
    role = eng.role[i]
    pts = eng.att_points(team, eng.pos)
    vel = eng.vel * eng.attack_dir[team]
    bx, by = eng.to_att(team, float(eng.ball[0]), float(eng.ball[1]))
    ball = np.array([bx, by])
    mates = [int(j) for j in eng.team_indices(team) if j != i]
    opps = eng.team_indices(1 - team)
    opp_pts = pts[opps]
    nearest = float(np.min(norms(opp_pts - ball, axis=1))) if len(opps) else 99.0
    pressure = float(np.clip((3.2 - nearest) / 3.2, 0, 1))
    line = offside_line(opp_pts, bx)
    options: list[Option] = []

    # Shooting: worth it when the chance is good, or from range with room to shoot.
    if mode in (None, "free_kick") and bx > 66:
        distance = math.hypot(LENGTH - bx, MID_Y - by)
        xg = expected_goal(bx, by, pressure=pressure)
        preference = (1.0 + 0.6 * role.on_ball.shoot_bias
                      + eng.effect(team, "mentality").shoot_preference)
        long_range = 18 < distance < 30
        if long_range:
            preference *= 0.45 + eng.a(i, "long_shots") / 140
        room = nearest > 3.0
        if (xg >= MIN_SHOT_XG or mode == "free_kick"
                or (long_range and room and xg >= LONG_SHOT_XG)):
            options.append((xg * preference * 0.95, "shot", None))

    # Passing: every teammate, plus balls into the path of forward runners.
    if mode != "shoot":
        options += _pass_options(eng, i, team, mates, pts, vel, ball, opp_pts, pressure, line, mode)

    # Carrying the ball.
    if mode is None:
        options += _carry_options(eng, i, team, ball, opp_pts, pressure)

    if not options:
        return
    decisions = eng.a(i, "decisions")
    temperature = (0.004 + 0.010 * (1 - decisions / 100) + 0.004 * (1 - float(eng.stamina[i]))
                   + max(0.0, eng.effect(team, "tempo").care))
    temperature *= eng.venue_bias(team, eng.defs.home_advantage.crowd.decisions * pressure)
    utilities = np.array([u for u, _, _ in options])
    weights = np.exp((utilities - utilities.max()) / temperature)
    choice = options[int(eng.rng.choice(len(options), p=weights / weights.sum()))]
    _, kind, payload = choice
    if kind == "shot":
        start_shot(eng, i)
    elif isinstance(payload, PassOption):
        start_pass(eng, i, payload.receiver, payload.target, payload.lofted,
                   "throw" if mode == "throw" else kind, pressure, payload.estimate)
    elif isinstance(payload, CarryOption):
        if payload.target != (float(bx), float(by)):  # shielding isn't a carry
            eng.emit("carry", team, i, urgent=payload.urgent, xa=round(float(bx), 1),
                     to_xa=round(payload.target[0], 1), to_ya=round(payload.target[1], 1))
        carry = np.array(eng.to_pitch(team, *payload.target), dtype=np.float64)
        eng.carry_target = carry
        eng.carry_urgent = payload.urgent
        eng.target[i] = carry
        eng.urgent[i] = payload.urgent
        eng.decide_at = eng.t + (0.9 if payload.urgent else 1.1)


def _pass_options(eng: "MatchEngine", i: int, team: int, mates: list[int], pts: np.ndarray,
                  vel: np.ndarray, ball: np.ndarray, opp_pts: np.ndarray, pressure: float,
                  line: float, mode: str | None) -> list[Option]:
    bx, by = ball
    directness = eng.effect(team, "passing").directness
    receivers: list[int] = []
    points: list[tuple[float, float]] = []
    kinds: list[str] = []
    for j in mates:
        jx, jy = pts[j]
        distance = math.hypot(jx - bx, jy - by)
        max_range = 25.0 if mode == "throw" else 40.0 if mode == "long_throw" else 60.0
        if distance < 3.0 or distance > max_range:
            continue
        if mode == "kickoff" and jx > bx:
            continue
        if eng.group[j] is PositionGroup.GK and distance > 30:
            continue  # no long back-passes to the keeper
        if distance > 32 and jx < bx - 5:
            continue  # nobody chips a long ball back towards his own goal
        lead = min(1.0, distance / 18) * 0.6
        receivers.append(j)
        points.append((jx + vel[j, 0] * lead, jy + vel[j, 1] * lead))
        kinds.append("pass")
        group = eng.group[j]
        if mode is None and (eng.running[j] or group in (PositionGroup.ST, PositionGroup.W)) \
                and jx > bx + 4 and jx > 45:
            receivers.append(j)
            points.append((min(jx + 7.0, LENGTH - 3), jy + vel[j, 1] * 0.8))
            kinds.append("through")
        if mode in (None, "corner", "long_throw") and bx > (70 if mode else 78) and \
                abs(by - MID_Y) > 12 and \
                jx > LENGTH - 17 and abs(jy - MID_Y) < 14:
            receivers.append(j)
            points.append((jx, jy))
            kinds.append("cross")
    if mode in ("corner", "long_throw"):
        keep = [k for k, kind in enumerate(kinds) if kind == "cross"]
        if not keep:
            keep = [k for k, j in enumerate(receivers) if pts[j][0] > LENGTH - 20]
        receivers = [receivers[k] for k in keep]
        points = [points[k] for k in keep]
        kinds = ["cross"] * len(keep)
    if not receivers:
        return []

    target = np.array(points)
    delta = target - ball
    length = np.maximum(norms(delta, axis=1), 1e-6)
    to_keeper = np.array([eng.group[j] is PositionGroup.GK for j in receivers])
    lofted = (np.array([k == "cross" for k in kinds]) | (length > 32)) & ~to_keeper
    unit = delta / length[:, None]
    ground_speed = np.clip(10 + 0.35 * length, 12, 26)
    flight = np.clip(0.9 + length / 25, 1.1, 2.8)
    speed = np.where(lofted, length / flight, ground_speed)
    rel = opp_pts[None, :, :] - ball[None, None, :]
    along = np.einsum("pkd,pd->pk", rel, unit)
    perp = norms(rel - along[..., None] * unit[:, None, :], axis=2)
    t_ball = np.maximum(along, 0) / speed[:, None]
    t_opp = np.maximum(perp - 1.0, 0) / 6.5 + 0.35
    valid = (along > 1.0) & (along < length[:, None] + 1.5)
    risk = np.where(valid, _sigmoid((t_ball - t_opp) * 4.0), 0.0)
    landing = along > length[:, None] - 4.0
    risk = np.where(lofted[:, None] & ~landing, risk * 0.25, risk)
    p_lane = np.prod(1 - 0.82 * eng.defs.passing.intercept_scale * risk, axis=1)
    marker = norms(target[:, None, :] - opp_pts[None, :, :], axis=2).min(axis=1) \
        if len(opp_pts) else np.full(len(target), 20.0)
    touch = np.array([eng.a(j, "first_touch") for j in receivers])
    p_receive = (0.55 + 0.45 * _sigmoid((marker - 1.8) * 1.3)) * (0.82 + 0.18 * touch / 100)
    skill = np.array([
        eng.a(i, "crossing") if kind == "cross" else
        eng.a(i, "long_passing") if dist > 25 else eng.a(i, "short_passing")
        for kind, dist in zip(kinds, length, strict=True)])
    p_exec = 1 - (0.015 + (length / 48) ** 2 * 0.45 * (1.25 - skill / 100)) * (1 + 0.8 * pressure)
    # Can the receiver get to the ball in time, and will an opponent get there first?
    recv_pts = np.array([pts[j] for j in receivers])
    recv_speed = np.array([eng.max_speed[j] for j in receivers]) * 0.9
    arrival = np.where(lofted, flight, length / ground_speed)
    recv_gap = norms(recv_pts - target, axis=1)
    p_reach = np.exp(-np.maximum(0.0, recv_gap - recv_speed * arrival) / 2.5)
    contest = _sigmoid((marker - recv_gap + 1.0) * 0.8)
    success = np.clip(p_lane * p_receive * p_exec * p_reach * (0.5 + 0.5 * contest), 0.02, 0.98)

    value = threat(target[:, 0], target[:, 1])
    value = np.where(np.array(kinds) == "cross", value * 1.1, value)
    loss = loss_cost(bx, by)
    utility = success * (value + RETAIN) - (1 - success) * loss
    forward = target[:, 0] - bx
    utility += 0.004 * directness * forward / 10
    if directness < 0:
        utility -= 0.012 * (length > 25)
    utility += 0.01 * eng.role[i].on_ball.pass_risk * (value - float(threat(bx, by)))
    offside = (target[:, 0] > line + 0.3) & (target[:, 0] > bx) & (target[:, 0] > 52.5)
    options: list[Option] = []
    decisions = eng.a(i, "decisions")
    for k, j in enumerate(receivers):
        receiver_x = pts[j][0]
        spots_offside = eng.rng.random() < 0.3 + 0.65 * decisions / 100
        if kinds[k] != "through" and receiver_x > line + 0.3 and receiver_x > bx and \
                receiver_x > 52.5 and spots_offside:
            continue  # sees the offside and doesn't play it
        if offside[k] and kinds[k] == "through" and spots_offside:
            continue
        options.append((float(utility[k]), kinds[k],
                        PassOption(j, (float(target[k, 0]), float(target[k, 1])),
                                   bool(lofted[k]), float(success[k]))))
    # A clearance is the last resort: heavy pressure close to our own goal.
    if mode is None and bx < 25 and pressure > 0.6:
        clear_to = (min(bx + 45, 80.0), float(np.clip(by + eng.rng.normal(0, 12), 4, 64)))
        clear_utility = 0.005 + 0.12 * pressure**2 * loss
        options.append((clear_utility, "clearance", PassOption(-1, clear_to, True, 0.3)))
    return options


def _carry_options(eng: "MatchEngine", i: int, team: int, ball: np.ndarray,
                   opp_pts: np.ndarray, pressure: float) -> list[Option]:
    bx, by = ball
    role = eng.role[i]
    skill = eng.a(i, "dribbling") * 0.7 + eng.a(i, "agility") * 0.3
    options: list[Option] = []
    toward_goal = by + (MID_Y - by) * (0.35 if bx > 70 else 0.1)
    for dy in (-6.0, 0.0, 6.0):
        aim = np.array([min(bx + 8.0, LENGTH - 2), float(np.clip(toward_goal + dy, 3, 65))])
        step = aim - ball
        step /= max(norm(step), 1e-6)
        probe = ball + step * 4.0
        blocker = float(np.min(norms(opp_pts - probe, axis=1))) if len(opp_pts) else 20.0
        free = blocker > 7.0
        # Taking a defender on succeeds about half the time; open grass is almost free.
        p_keep = 0.97 if free else float(_sigmoid((skill - 70) / 15 + (blocker - 4.0) * 0.7))
        value = float(threat(aim[0], aim[1]))
        utility = p_keep * (value + RETAIN * 0.8) - (1 - p_keep) * loss_cost(bx, by)
        utility += 0.012 * role.on_ball.dribble_bias + (0.004 if free else 0.0)
        options.append((utility, "carry",
                        CarryOption((float(aim[0]), float(aim[1])), not free or bx > 60)))
    # Shielding: keep the ball and wait for support (not an option in the final third,
    # where standing still just lets the defence organise).
    if bx < 70:
        keep = 1 - 0.7 * pressure
        utility = keep * (0.8 * float(threat(bx, by)) + RETAIN) - (1 - keep) * loss_cost(bx, by)
        options.append((utility, "carry", CarryOption((float(bx), float(by)), False)))
    return options


# --- passes ----------------------------------------------------------------------------


def start_pass(eng: "MatchEngine", i: int, j: int, target: tuple[float, float], lofted: bool,
               kind: str, pressure: float = 0.0, estimate: float = 1.0) -> None:
    team = int(eng.team_of[i])
    bx, by = eng.to_att(team, float(eng.ball[0]), float(eng.ball[1]))
    tx, ty = target
    distance = max(math.hypot(tx - bx, ty - by), 0.5)
    skill = (eng.a(i, "crossing") if kind == "cross" else eng.a(i, "long_passing")
             if distance > 25 else eng.a(i, "short_passing"))
    if kind == "throw":
        skill = 85.0
    fatigue = 1 - float(eng.stamina[i])
    ex = eng.defs.passing.execution
    spread = (ex.base + ex.skill * (1 - skill / 100) + ex.pressure * pressure
              + ex.fatigue * fatigue + ex.per_metre * max(0.0, distance - 15)
              + (ex.lofted if lofted else 0.0))
    spread *= 1 + eng.effect(team, "tempo").hurry  # hurried passes go astray more often
    spread *= eng.venue_bias(team, eng.defs.home_advantage.crowd.execution * pressure)
    angle_error = eng.rng.normal(0, spread)
    length_error = float(np.clip(eng.rng.normal(1.0, ex.length_skill * (1.2 - skill / 100)
                                                + ex.length_per_metre * distance), 0.5, 1.6))
    angle = math.atan2(ty - by, tx - bx) + angle_error
    reach = distance * length_error
    ax, ay = bx + math.cos(angle) * reach, by + math.sin(angle) * reach
    aim = np.array(eng.to_pitch(team, ax, ay))
    direction = aim - eng.ball
    direction /= max(float(norm(direction)), 1e-6)
    if lofted:
        flight = float(np.clip(0.9 + reach / 25, 1.1, 2.8))
        eng.ball_v = direction * reach / flight
        eng.ball_vz = 9.81 * flight / 2
        eng.ball_z = 0.1
    else:
        # Towards our own goal the ball is played softly, to arrive gently at the man.
        arrive = 2.0 if (tx < 20 and tx < bx) else 5.0
        eng.ball_v = direction * math.sqrt(arrive**2 + 2 * 4.0 * reach)
        eng.ball_vz = 0.0
        eng.ball_z = 0.0
    eng.owner = -1
    eng.state = "pass"
    eng.last_touch = i
    eng.carry_target = None
    eng.pass_info = PassInfo(i, j, (float(aim[0]), float(aim[1])), lofted, kind, tried={i},
                             estimate=estimate, restart=eng.taking_restart)
    eng.emit("pass", team, i, kind=kind, lofted=lofted, estimate=round(estimate, 3),
             length=round(distance, 1), xa=round(bx, 1), receiver=j)
    if kind != "clearance":
        eng.stats[team].passes += 1
        eng.lines[eng.players[i].player_id].passes += 1
        if eng.possessions and eng.possessions[-1].team == team:
            eng.possessions[-1].passes += 1
    passer = eng.players[i].player.short_name
    if kind == "through" and j >= 0:
        eng.commentate(team, f"{passer} slides it through for {eng.players[j].player.short_name}",
                       gap=2.0)
    elif kind == "cross":
        eng.commentate(team, f"{passer} whips a cross into the box", gap=2.0)
    elif kind == "clearance":
        eng.commentate(team, f"{passer} clears the danger", gap=4.0)
    if j >= 0:
        eng.target[j] = aim
        eng.urgent[j] = True
        _check_offside(eng, i, j, team, bx)


def _check_offside(eng: "MatchEngine", i: int, j: int, team: int, ball_x: float) -> None:
    rx, ry = eng.to_att(team, float(eng.pos[j, 0]), float(eng.pos[j, 1]))
    opp_pts = eng.att_points(team, eng.pos[eng.team_indices(1 - team)])
    info = eng.pass_info
    if info is not None and (info.kind == "throw" or info.restart in NO_OFFSIDE):
        return  # no offside from a throw-in, goal kick or corner (Law 11)
    if rx > offside_line(opp_pts, ball_x) + 0.3 and rx > ball_x and rx > 52.5:
        eng.stats[team].offsides += 1
        eng.emit("offside", team, j)
        eng._announce("offside", team, f"Offside: {eng.players[j].player.name}")
        eng.award_restart("free_kick", 1 - team, (float(eng.pos[j, 0]), float(eng.pos[j, 1])),
                          "offside")


def resolve_loose_or_pass(eng: "MatchEngine") -> None:
    info = eng.pass_info
    if info is not None and info.kind == "cross" and _aerial(eng, info):
        return
    if info is not None and info.lofted and info.kind in ("pass", "through") \
            and _long_ball_contest(eng, info):
        return
    if eng.ball_z > 2.0:
        return
    path = _path_distance(eng)
    reach = np.full(len(path), CONTROL_RADIUS)
    for side in (0, 1):
        keeper = eng.keeper(side)
        if keeper is not None and in_own_box(*eng.to_att(side, float(eng.ball[0]),
                                                          float(eng.ball[1]))):
            reach[keeper] = KEEPER_REACH
    near = np.flatnonzero(eng.active & (path < reach))
    if len(near):
        order = near[np.argsort(path[near])]
        speed = float(norm(eng.ball_v))
        for c in (int(x) for x in order):
            closeness = float(np.sqrt(max(0.0, 1 - path[c] / reach[c])))
            if info is not None and c in info.tried:
                continue
            keeper_home = eng.group[c] is PositionGroup.GK and in_own_box(
                *eng.to_att(int(eng.team_of[c]), float(eng.ball[0]), float(eng.ball[1])))
            if info is not None:
                if c != info.receiver:  # the intended receiver keeps trying while in reach
                    info.tried.add(c)
                same = eng.team_of[c] == eng.team_of[info.passer]
                if keeper_home:  # keepers gather balls in their own box almost every time
                    p = 0.93 + 0.06 * eng.a(c, "gk_handling") / 100
                    if eng.rng.random() < p:
                        _take(eng, c, info)
                        return
                    continue
                if same:
                    control = eng.defs.passing.control
                    base = control.receiver if c == info.receiver else control.teammate
                    p = base * (0.9 + 0.1 * eng.a(c, "first_touch") / 100)
                    p *= 1 - max(0.0, speed - 15) / 30
                    p *= 1 - _touch_pressure(eng, c) * (1 - eng.a(c, "first_touch") / 100)
                    info.tried.add(c)  # one touch: a miscontrol leaves the ball loose
                    if eng.rng.random() < max(0.05, p):
                        _take(eng, c, info)
                    else:
                        _heavy_touch(eng, c, info)
                    return
                else:
                    p = (0.18 + 0.4 * eng.a(c, "interceptions") / 100
                         + 0.1 * eng.a(c, "anticipation") / 100) * closeness
                    p *= eng.defs.passing.intercept_scale
                    p *= float(np.clip(1.2 - speed / 25, 0.4, 1.0))
                    if info.lofted:
                        p *= 0.7
            else:
                same = False
                p = 0.55 + 0.35 * eng.a(c, "first_touch") / 100
                if keeper_home:
                    p = 0.95
            if eng.rng.random() < max(0.05, p):
                _take(eng, c, info)
                return
    if eng.state == "pass" and float(norm(eng.ball_v)) < 1.0 and eng.ball_z <= 0:
        eng.state = "loose"
        eng.stopped_pass = (info, eng.t) if info is not None else None
        eng.pass_info = None


def _touch_pressure(eng: "MatchEngine", c: int) -> float:
    """0-1: how close the nearest opponent is to a player taking the ball, scaled so an
    opponent on top of him costs the full control penalty."""
    control = eng.defs.passing.control
    opps = eng.team_indices(1 - int(eng.team_of[c]))
    if not len(opps):
        return 0.0
    nearest = float(np.min(norms(eng.pos[opps] - eng.pos[c], axis=1)))
    closeness = max(0.0, (control.pressure_radius - nearest) / control.pressure_radius)
    return control.pressure_penalty * closeness


def _heavy_touch(eng: "MatchEngine", c: int, info: PassInfo) -> None:
    """The ball bounces off a poor first touch and runs loose."""
    low, high = eng.defs.passing.control.heavy_touch_speed
    angle = float(eng.rng.uniform(0, 2 * math.pi))
    eng.ball_v = np.array([math.cos(angle), math.sin(angle)]) * float(eng.rng.uniform(low, high))
    eng.ball_z = 0.0
    eng.ball_vz = 0.0
    eng.last_touch = c
    eng.state = "loose"
    eng.stopped_pass = (info, eng.t)  # still a completed pass if a teammate gathers it
    eng.pass_info = None
    eng.emit("heavy_touch", int(eng.team_of[c]), c)


def _path_distance(eng: "MatchEngine") -> np.ndarray:
    """Each player's distance to the ball's path during the last tick, so a fast ball can't
    skip past a player between two ticks."""
    start, end = eng.prev_ball, eng.ball
    seg = end - start
    length_sq = float(seg @ seg)
    if length_sq < 1e-9:
        result: np.ndarray = norms(eng.pos - end, axis=1)
        return result
    t = np.clip(((eng.pos - start) @ seg) / length_sq, 0, 1)
    closest = start + t[:, None] * seg[None, :]
    result = norms(eng.pos - closest, axis=1)
    return result


def _take(eng: "MatchEngine", c: int, info: PassInfo | None) -> None:
    team = int(eng.team_of[c])
    if info is None and eng.stopped_pass is not None:
        # A pass that ran out of pace, gathered a moment later by its own side, still counts.
        stopped, when = eng.stopped_pass
        eng.stopped_pass = None
        if eng.t - when < 3.0 and int(eng.team_of[stopped.passer]) == team:
            info = stopped
    how = "loose"
    if isinstance(info, PassInfo):
        passer_team = int(eng.team_of[info.passer])
        if passer_team == team and info.kind != "clearance":
            eng.stats[team].passes_completed += 1
            eng.lines[eng.players[info.passer].player_id].passes_completed += 1
            eng.last_completed_pass = (info.passer, c, eng.t)
            eng.emit("pass_result", team, info.passer, result="complete", kind=info.kind)
            how = "pass"
        elif passer_team != team:
            won_at, _ = eng.to_att(team, float(eng.ball[0]), float(eng.ball[1]))
            if info.kind != "clearance" and cut_out(eng, info):  # a clearance isn't a pass
                eng.lines[eng.players[c].player_id].interceptions += 1
                eng.emit("pass_result", passer_team, info.passer, result="intercepted",
                         kind=info.kind, by=c, by_xa=round(won_at, 1))
                eng.commentate(team, f"{eng.players[c].player.short_name} reads it and intercepts")
                how = "interception"
            else:  # overhit or off target, so it came to him: Opta's ball recovery
                eng.emit("pass_result", passer_team, info.passer, result="recovered",
                         kind=info.kind, by=c, by_xa=round(won_at, 1))
                how = "recovery"
    gain_possession(eng, c, how=how)


def cut_out(eng: "MatchEngine", info: PassInfo) -> bool:
    """Was the ball still on course for the pass's target area, and not yet past it, when an
    opponent took it? Then he got into its path: an interception."""
    speed = float(norm(eng.ball_v))
    if speed < 1e-6:
        return False
    radius = eng.defs.passing.target_area
    ahead = np.asarray(info.target, dtype=float) - eng.ball
    along = float(ahead @ eng.ball_v) / speed
    across = math.sqrt(max(0.0, float(ahead @ ahead) - along * along))
    return along > -radius and across <= radius


def _aerial(eng: "MatchEngine", info: PassInfo) -> bool:
    """A cross arriving in the box: keeper claim, then a heading duel."""
    landing = np.array(info.target)
    if float(norm(eng.ball - landing)) > 2.5 or eng.ball_z > 2.8:
        return False
    team = int(eng.team_of[info.passer])
    keeper = eng.keeper(1 - team)
    dx, _ = eng.to_att(1 - team, float(eng.ball[0]), float(eng.ball[1]))
    if keeper is not None and dx < 7 and float(norm(eng.pos[keeper] - eng.ball)) < 5:
        claim = 0.3 + 0.45 * eng.a(keeper, "gk_command_of_area") / 100
        if eng.rng.random() < claim:
            eng.emit("aerial", 1 - team, keeper, won="keeper")
            eng._announce("claim", 1 - team, f"{eng.players[keeper].player.name} claims the cross")
            gain_possession(eng, keeper, delay=2.0, how="claim")
            return True
    near = np.flatnonzero(eng.active & (norms(eng.pos - eng.ball, axis=1) < 3.0))
    outfield = [int(k) for k in near if eng.group[k] is not PositionGroup.GK]
    attackers = [k for k in outfield if eng.team_of[k] == team]
    defenders = [k for k in outfield if eng.team_of[k] != team]
    if not attackers and not defenders:
        eng.pass_info = None
        eng.state = "loose"
        return True

    def aerial(k: int) -> float:
        height = eng.players[k].player.height_cm
        return (0.4 * eng.a(k, "heading_accuracy") + 0.3 * eng.a(k, "jumping")
                + 0.15 * eng.a(k, "strength") + 0.15 * eng.a(k, "bravery") + 0.6 * (height - 180))

    best_a = max(attackers, key=aerial) if attackers else None
    best_d = max(defenders, key=aerial) if defenders else None
    if (best_a is not None and best_d is not None
            and eng.rng.random() < eng.defs.duels.aerial_foul_chance):
        eng.pass_info = None
        duels.aerial_foul(eng, best_a, best_d)
        return True
    if best_a is not None and (best_d is None or eng.rng.random() < float(
            _sigmoid((aerial(best_a) - aerial(best_d)) / 8))):
        eng.pass_info = None
        eng.last_completed_pass = (info.passer, best_a, eng.t)
        eng.stats[team].passes_completed += 1
        eng.lines[eng.players[info.passer].player_id].passes_completed += 1
        eng.emit("aerial", team, best_a, won="attack", contested=best_d is not None)
        eng.emit("pass_result", team, info.passer, result="complete", kind=info.kind)
        eng.ball_z = 0.0
        hx, hy = eng.to_att(team, float(eng.ball[0]), float(eng.ball[1]))
        if expected_goal(hx, hy, header=True) >= HEADER_ON_GOAL_XG:
            eng.owner = best_a
            start_shot(eng, best_a, header=True)
        else:  # no angle for goal: he nods it down for a teammate
            angle = float(eng.rng.normal(math.pi, 0.8))
            eng.ball_v = np.array([math.cos(angle) * eng.attack_dir[team], math.sin(angle)]) \
                * float(eng.rng.uniform(3, 7))
            eng.ball_vz = float(eng.rng.uniform(0.5, 2))
            eng.ball_z = 1.5
            eng.last_touch = best_a
            eng.owner = -1
            eng.state = "loose"
            eng.emit("knock_down", team, best_a)
        return True
    assert best_d is not None
    eng.emit("aerial", 1 - team, best_d, won="defence", contested=best_a is not None)
    _clear(eng, best_d)
    return True


def _aerial_strength(eng: "MatchEngine", k: int) -> float:
    height = eng.players[k].player.height_cm
    return (0.4 * eng.a(k, "heading_accuracy") + 0.3 * eng.a(k, "jumping")
            + 0.15 * eng.a(k, "strength") + 0.15 * eng.a(k, "bravery") + 0.6 * (height - 180))


def _long_ball_contest(eng: "MatchEngine", info: PassInfo) -> bool:
    """A long ball dropping near an opponent: a header decides who gets it. The receiver
    may head it down to himself; an opponent who wins it heads it away as a second ball."""
    landing = np.array(info.target)
    if float(norm(eng.ball - landing)) > 2.5 or eng.ball_z > 2.8 or info.receiver < 0:
        return False
    team = int(eng.team_of[info.passer])
    radius = eng.defs.passing.aerial_contest_radius
    rivals = [int(k) for k in eng.team_indices(1 - team) if eng.group[k] is not PositionGroup.GK
              and float(norm(eng.pos[k] - eng.ball)) < radius]
    receiver = info.receiver
    if not rivals or float(norm(eng.pos[receiver] - eng.ball)) > radius:
        return False
    rival = max(rivals, key=lambda k: _aerial_strength(eng, k))
    if eng.rng.random() < eng.defs.duels.aerial_foul_chance:
        eng.pass_info = None
        duels.aerial_foul(eng, receiver, rival)
        return True
    won = eng.rng.random() < float(_sigmoid(
        (_aerial_strength(eng, receiver) - _aerial_strength(eng, rival)) / 8))
    eng.emit("aerial", team if won else 1 - team, receiver if won else rival,
             won="attack" if won else "defence", contested=True, long_ball=True)
    if won:
        if eng.rng.random() < eng.defs.passing.header_to_feet:
            _take(eng, receiver, info)
        else:
            _heavy_touch(eng, receiver, info)
        return True
    info.tried.add(receiver)
    _clear(eng, rival, headed=True)
    return True


def _clear(eng: "MatchEngine", k: int, headed: bool = False) -> None:
    team = int(eng.team_of[k])
    if eng.rng.random() < eng.defs.passing.clearance_wide_share:  # put it out wide
        angle = float(eng.rng.uniform(0.7, 1.2)) * (1.0 if eng.rng.random() < 0.5 else -1.0)
    else:
        angle = float(eng.rng.normal(0, 0.5))
    direction = np.array([math.cos(angle) * eng.attack_dir[team], math.sin(angle)])
    eng.ball_v = direction * float(eng.rng.uniform(8, 14) if headed else eng.rng.uniform(13, 20))
    eng.ball_vz = float(eng.rng.uniform(2, 5) if headed else eng.rng.uniform(3, 7))
    eng.ball_z = 1.0
    eng.owner = -1
    eng.state = "loose"
    eng.pass_info = None
    eng.last_touch = k
    eng.emit("clearance", team, k)


# --- shots -----------------------------------------------------------------------------


def start_shot(eng: "MatchEngine", i: int, header: bool = False, penalty: bool = False,
               free_kick: bool = False) -> None:
    team = int(eng.team_of[i])
    bx, by = eng.to_att(team, float(eng.ball[0]), float(eng.ball[1]))
    distance = math.hypot(LENGTH - bx, MID_Y - by)
    opps = eng.team_indices(1 - team)
    opp_pts = eng.att_points(team, eng.pos[opps])
    nearest = (float(np.min(norms(opp_pts - np.array([bx, by]), axis=1)))
               if len(opps) else 9.0)
    pressure = 0.0 if (penalty or free_kick) else float(np.clip((5.0 - nearest) / 5.0, 0, 1))
    pressure *= 1.2 - eng.a(i, "composure") / 100
    cone = 0 if (penalty or free_kick) else _defenders_in_cone(eng, team, bx, by, opp_pts)
    keeper = eng.keeper(1 - team)
    gk = (np.mean([eng.a(keeper, a) for a in ("gk_reflexes", "gk_diving", "gk_positioning")])
          if keeper is not None else 25.0)
    if penalty:
        skill = eng.a(i, "penalties")
        xg = 0.76
        p_goal = penalty_probability(eng.players[i].player,
                                     eng.players[keeper].player if keeper is not None else None)
        p_on = 0.9
    else:
        if header:
            skill = eng.a(i, "heading_accuracy")
        elif free_kick:
            skill = eng.a(i, "free_kicks")
        elif distance > 18:
            skill = eng.a(i, "long_shots")
        else:
            skill = eng.a(i, "finishing")
        xg = expected_goal(bx, by, header=header, pressure=pressure) * 0.55**min(cone, 3)
        if free_kick:
            xg = max(0.02, 0.09 - 0.0025 * max(distance - 18, 0))
        p_on = float(np.clip(0.20 + 0.40 * skill / 100 - 0.012 * max(distance - 10, 0)
                             - 0.15 * pressure + 0.35 * math.exp(-distance / 4), 0.12, 0.92))
        p_goal = xg * (0.7 + 0.35 * skill / 100) * (1.3 - 0.6 * gk / 100)
    p_on = max(p_on, min(0.95, p_goal / 0.95))
    blockers = 0
    if not (penalty or free_kick):
        goal_dir = np.array([LENGTH - bx, MID_Y - by]) / max(distance, 1e-6)
        rel = opp_pts - np.array([bx, by])
        along = rel @ goal_dir
        perp = np.abs(rel[:, 0] * goal_dir[1] - rel[:, 1] * goal_dir[0])
        blockers = int(np.sum((along > 0.8) & (along < min(distance, 14)) & (perp < 0.9)))
    block_chance = min(0.6, 0.28 * blockers)
    xg = float(p_goal * (1 - block_chance))  # the chance's real scoring probability
    roll = eng.rng.random()
    if blockers and eng.rng.random() < block_chance:
        outcome = "blocked"
    elif roll < p_goal:
        outcome = "goal"
    elif roll < p_on:
        outcome = "saved"
    else:
        outcome = "off"

    # Where the ball goes (attacking frame, on the goal line).
    if outcome == "off":
        if eng.rng.random() < 0.5:
            wide = GOAL_HALF + float(eng.rng.uniform(0.3, 3))
            ty = MID_Y + float(eng.rng.choice([-1, 1])) * wide
            tz = float(eng.rng.uniform(0.2, 2.0))
        else:
            ty = MID_Y + float(eng.rng.uniform(-GOAL_HALF, GOAL_HALF))
            tz = float(eng.rng.uniform(2.7, 4.5))
    else:
        ty = MID_Y + float(eng.rng.uniform(-GOAL_HALF + 0.3, GOAL_HALF - 0.3))
        tz = float(eng.rng.uniform(0.2, 2.1))
        if outcome == "saved":
            window = _save_window(eng, team, keeper, bx, by)
            if window is None:  # no shot on target passes within his reach: he's beaten
                outcome = "goal"
            else:  # a saved shot is one he can reach: the same draw, placed in his window
                low, high = window
                ty = low + (ty - (MID_Y - GOAL_HALF + 0.3)) / (2 * GOAL_HALF - 0.6) * (high - low)
    speed = 22.0 if penalty else (13.0 if header else 17.0 + 13.0 * eng.a(i, "shot_power") / 100)
    aim = np.array(eng.to_pitch(team, LENGTH + 0.5, ty))
    direction = aim - eng.ball
    travel = max(float(norm(direction)), 0.5)
    direction /= travel
    flight = travel / speed
    eng.ball_v = direction * speed
    eng.ball_z = 0.5 if header else 0.1
    eng.ball_vz = (tz - eng.ball_z + 0.5 * 9.81 * flight**2) / flight
    resolve = travel
    if outcome == "saved" and keeper is not None:
        kx, ky = eng.to_att(team, float(eng.pos[keeper, 0]), float(eng.pos[keeper, 1]))
        # The save happens in front of the goal line, never behind it.
        resolve = max(0.5, min(math.hypot(kx - bx, ky - by) - 0.5, travel - 1.5))
        # He goes for the point where the shot will pass him, and keeps going until it does.
        path = aim - eng.ball
        along = float(np.clip((eng.pos[keeper] - eng.ball) @ path / max(float(path @ path), 1e-9),
                              0.0, 1.0))
        eng.target[keeper] = eng.ball + along * path
    elif outcome == "blocked":
        resolve = float(eng.rng.uniform(min(1.5, travel / 2), max(min(8.0, travel), 1.5)))
        resolve = min(resolve, max(0.3, travel - 1.5))  # blocked in front of the goal line
    eng.owner = -1
    eng.state = "shot"
    eng.last_touch = i
    eng.carry_target = None
    eng.shot_info = ShotInfo(i, outcome, xg, keeper, resolve, header=header, penalty=penalty)
    outfield = [k for k, j in enumerate(opps.tolist()) if j != keeper]
    ball = np.array([bx, by])
    eng.emit(
        "shot", team, i, xg=round(xg, 4), outcome=outcome, header=header, penalty=penalty,
        free_kick=free_kick, distance=round(distance, 1), xa=round(bx, 1), ya=round(by, 1),
        blockers=blockers,
        goal_side=int(np.sum(opp_pts[outfield, 0] > bx)) if outfield else 0,
        nearest=round(float(np.min(norms(opp_pts[outfield] - ball, axis=1))), 1)
        if outfield else 99.0,
    )
    if eng.possessions and eng.possessions[-1].team == team:
        eng.possessions[-1].shots += 1
    line = eng.lines[eng.players[i].player_id]
    line.shots += 1
    eng.stats[team].shots += 1
    eng.stats[team].xg += xg
    eng.player_xg[line.player_id] = eng.player_xg.get(line.player_id, 0.0) + xg
    if outcome in ("goal", "saved"):
        line.shots_on_target += 1
        eng.stats[team].shots_on_target += 1
    name = eng.players[i].player.name
    what = "heads" if header else "shoots"
    if penalty:
        eng._announce("shot", team, f"{name} steps up...")
    else:
        eng._announce("shot", team, f"{name} {what} from {distance:.0f} m")


def _save_window(eng: "MatchEngine", team: int, keeper: int | None, bx: float,
                 by: float) -> tuple[float, float] | None:
    """The stretch of the goal mouth (attacking frame) a shot from (bx, by) can be aimed at and
    still pass within the keeper's dive, or None if no shot on target does."""
    if keeper is None:
        return None
    kx, ky = eng.to_att(team, float(eng.pos[keeper, 0]), float(eng.pos[keeper, 1]))
    depth = kx - bx
    if depth < 0.5:  # he's level with the shooter, or behind him
        return None
    scale = (LENGTH + 0.5 - bx) / depth  # his depth to the goal line, along lines from the ball
    centre = by + (ky - by) * scale
    low = max(MID_Y - GOAL_HALF + 0.3, centre - KEEPER_DIVE * scale)
    high = min(MID_Y + GOAL_HALF - 0.3, centre + KEEPER_DIVE * scale)
    return (low, high) if low <= high else None


def _defenders_in_cone(eng: "MatchEngine", team: int, bx: float, by: float,
                       opp_pts: np.ndarray) -> int:
    """Outfield opponents inside the triangle between the ball and the goal posts."""
    count = 0
    keeper = eng.keeper(1 - team)
    opps = eng.team_indices(1 - team)
    for k, (x, y) in zip(opps.tolist(), opp_pts.tolist(), strict=True):
        if k == keeper or x <= bx:
            continue
        share = (x - bx) / max(LENGTH - bx, 0.1)
        low = by + share * (MID_Y - GOAL_HALF - by)
        high = by + share * (MID_Y + GOAL_HALF - by)
        if min(low, high) - 0.5 <= y <= max(low, high) + 0.5:
            count += 1
    return count


def shot_tick(eng: "MatchEngine") -> None:
    info = eng.shot_info
    if info is None or info.outcome not in ("saved", "blocked"):
        return
    if info.travelled < info.resolve_distance:
        return
    team = int(eng.team_of[info.shooter])
    if info.outcome == "blocked":
        eng.shot_info = None
        blockers = eng.team_indices(1 - team)
        blocker = int(blockers[np.argmin(norms(eng.pos[blockers] - eng.ball, axis=1))])
        roll = eng.rng.random()
        eng.emit("block", 1 - team, blocker,
                 how="cleared" if roll < 0.45 else "corner" if roll < 0.75 else "loose")
        if roll < 0.45:  # the blocker gets it away
            eng._announce("block", 1 - team, f"Blocked by {eng.players[blocker].player.name}")
            _clear(eng, blocker)
        elif roll < 0.75:  # deflected behind
            eng._announce("block", 1 - team, "Blocked, out for a corner")
            eng.stats[team].corners += 1
            line_x = LENGTH if eng.attack_dir[team] > 0 else 0.0
            corner_y = 0.0 if float(eng.ball[1]) < MID_Y else 68.0
            eng.award_restart("corner", team, (line_x, corner_y))
        else:  # a genuine loose rebound, back out towards the edge of the box
            eng._announce("block", 1 - team, "Blocked!")
            angle = float(eng.rng.normal(0, 0.9))
            back = -eng.attack_dir[team]
            direction = np.array([math.cos(angle) * back, math.sin(angle)])
            eng.ball_v = direction * float(eng.rng.uniform(4, 10))
            eng.ball_vz = float(eng.rng.uniform(0, 3))
            eng.last_touch = blocker
            eng.state = "loose"
        return
    keeper = info.keeper
    eng.shot_info = None
    if keeper is None:
        eng.state = "loose"
        return
    eng.lines[eng.players[keeper].player_id].saves += 1
    kname = eng.players[keeper].player.name
    if eng.rng.random() < 0.5 + 0.4 * eng.a(keeper, "gk_handling") / 100:
        # The keeper dives (at most KEEPER_DIVE metres) and the ball ends up in his hands.
        reach = eng.ball - eng.pos[keeper]
        distance = float(norm(reach))
        if distance > 1e-6:
            eng.pos[keeper] = eng.pos[keeper] + reach / distance * min(distance, KEEPER_DIVE)
        eng.emit("save", 1 - team, keeper, how="catch",
                 teleported=round(max(0.0, distance - KEEPER_DIVE), 1))
        eng._announce("save", 1 - team, f"Saved by {kname}")
        eng.ball = eng.pos[keeper].copy()
        gain_possession(eng, keeper, delay=float(eng.rng.uniform(2.5, 4.5)), how="save")
        return
    eng.last_touch = keeper
    if eng.rng.random() < 0.3:
        eng.emit("save", 1 - team, keeper, how="tip", teleported=0.0)
        eng._announce("save", 1 - team, f"{kname} tips it behind for a corner!")
        eng.stats[team].corners += 1
        line_x = LENGTH if eng.attack_dir[team] > 0 else 0.0
        corner_y = 0.0 if float(eng.ball[1]) < MID_Y else 68.0
        eng.award_restart("corner", team, (line_x, corner_y))
        return
    eng.emit("save", 1 - team, keeper, how="parry", teleported=0.0)
    eng._announce("save", 1 - team, f"{kname} parries it away!")
    back = -eng.attack_dir[team]  # away from the goal being attacked
    side = 1.0 if float(eng.ball[1]) >= MID_Y else -1.0  # keepers push shots wide
    eng.ball_v = np.array([back * float(eng.rng.uniform(3, 8)),
                           side * float(eng.rng.uniform(8, 15))])
    eng.ball_vz = float(eng.rng.uniform(0.5, 3))
    eng.state = "loose"


# --- substitutions and ratings ---------------------------------------------------------


def ai_substitutions(eng: "MatchEngine", team: int) -> None:
    if eng.subs_used[team] >= MAX_SUBS or not eng.bench[team]:
        return
    waiting = eng.pending_for(team)
    going = {off for off, _ in waiting}
    coming = {on for _, on in waiting}
    tired = sorted((int(i) for i in eng.team_indices(team)
                    if eng.group[i] is not PositionGroup.GK and eng.stamina[i] < 0.62
                    and i != eng.owner and eng.players[i].player_id not in going),
                   key=lambda i: float(eng.stamina[i]))
    for i in tired[:2]:
        if eng.subs_used[team] >= MAX_SUBS or not eng.bench[team]:
            return
        bench = [sp for sp in eng.bench[team] if sp.player_id not in coming]
        same = [sp for sp in bench if sp.group is eng.group[i]]
        pool = same or [sp for sp in bench if sp.group is not PositionGroup.GK]
        if not pool:
            return
        incoming = max(pool, key=lambda sp: sp.rating)
        coming.add(incoming.player_id)
        eng.substitute(team, eng.players[i].player_id, incoming.player_id)


def rate_players(eng: "MatchEngine") -> None:
    for team in (0, 1):
        result = (eng.score[team] > eng.score[1 - team]) - (eng.score[team] < eng.score[1 - team])
        conceded = eng.score[1 - team]
        club = eng.sheets[team].club_id
        groups = {sp.player_id: sp.group for sp in [*eng.sheets[team].starters,
                                                    *eng.sheets[team].bench]}
        for line in eng.lines.values():
            if line.club_id != club:
                continue
            group = groups.get(line.player_id, PositionGroup.CM)
            line.rating = match_rating(line, group, result, conceded, line.minutes)
