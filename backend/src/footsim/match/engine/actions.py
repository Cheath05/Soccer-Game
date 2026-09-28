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
from footsim.match.engine.behaviours import offside_line
from footsim.match.engine.pitch import (
    GOAL_HALF,
    LENGTH,
    MID_Y,
    PENALTY_SPOT,
    expected_goal,
    in_box,
    in_own_box,
    loss_cost,
    threat,
)
from footsim.match.engine.state import MAX_SUBS, PassInfo, Restart, ShotInfo
from footsim.match.penalties import penalty_probability
from footsim.match.quick import INJURIES, INJURY_WEIGHTS
from footsim.match.report import Injury, MatchEvent

if TYPE_CHECKING:
    from footsim.match.engine.engine import MatchEngine

RETAIN = 0.015  # value of simply keeping the ball
CONTROL_RADIUS = 1.3
KEEPER_REACH = 2.4  # arms: keepers gather balls further away in their own box
TACKLE_RADIUS = 2.0
DIRECTNESS = {"short": -1.0, "mixed": 0.0, "direct": 1.0}
TEMPO_DELAY = {"slow": 2.0, "normal": 1.6, "fast": 1.15}  # s on the ball before acting
MIN_SHOT_XG = 0.05  # open play: nobody shoots from hopeless positions
MENTALITY_SHOOT = {"defensive": -0.1, "balanced": 0.0, "attacking": 0.12}


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


def gain_possession(eng: "MatchEngine", i: int, delay: float | None = None) -> None:
    if eng.last_touch < 0 or int(eng.team_of[eng.last_touch]) != int(eng.team_of[i]):
        eng.turnover_at = eng.t
    eng.owner = i
    eng.state = "owned"
    eng.ball_z = 0.0
    eng.ball_vz = 0.0
    eng.last_touch = i
    eng.pass_info = None
    eng.carry_target = None
    eng.carry_urgent = False
    if delay is None:
        tempo = TEMPO_DELAY.get(eng.instructions[int(eng.team_of[i])].get("tempo", ""), 1.6)
        delay = tempo + 0.35 * (1 - eng.a(i, "first_touch") / 100) + float(eng.rng.uniform(0, 0.2))
    eng.decide_at = eng.t + delay


def owner_tick(eng: "MatchEngine") -> None:
    i = eng.owner
    if _tackles(eng, i):
        return
    team = int(eng.team_of[i])
    opp = eng.team_indices(1 - team)
    pressed = len(opp) and float(np.min(np.linalg.norm(eng.pos[opp] - eng.pos[i], axis=1))) < 1.8
    if eng.t >= eng.decide_at or (pressed and eng.t >= eng.decide_at - 0.25):
        decide(eng, i)


# --- decisions -------------------------------------------------------------------------


def decide(eng: "MatchEngine", i: int, mode: str | None = None) -> None:
    """Choose and start the owner's next action. ``mode`` restricts options at restarts."""
    team = int(eng.team_of[i])
    ins = eng.instructions[team]
    role = eng.role[i]
    pts = eng.att_points(team, eng.pos)
    vel = eng.vel * eng.attack_dir[team]
    bx, by = eng.to_att(team, float(eng.ball[0]), float(eng.ball[1]))
    ball = np.array([bx, by])
    mates = [int(j) for j in eng.team_indices(team) if j != i]
    opps = eng.team_indices(1 - team)
    opp_pts = pts[opps]
    nearest = float(np.min(np.linalg.norm(opp_pts - ball, axis=1))) if len(opps) else 99.0
    pressure = float(np.clip((3.2 - nearest) / 3.2, 0, 1))
    line = offside_line(opp_pts, bx)
    options: list[Option] = []

    # Shooting.
    if mode in (None, "free_kick") and bx > 66:
        distance = math.hypot(LENGTH - bx, MID_Y - by)
        xg = expected_goal(bx, by, pressure=pressure)
        preference = 1.0 + 0.6 * role.on_ball.shoot_bias + MENTALITY_SHOOT.get(
            ins.get("mentality", ""), 0.0)
        if distance > 18:
            preference *= 0.45 + eng.a(i, "long_shots") / 140
        if xg >= MIN_SHOT_XG or mode == "free_kick":
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
    temperature = 0.004 + 0.010 * (1 - decisions / 100) + 0.004 * (1 - float(eng.stamina[i]))
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
    ins = eng.instructions[team]
    directness = DIRECTNESS.get(ins.get("passing", ""), 0.0)
    fast = ins.get("tempo") == "fast"
    receivers: list[int] = []
    points: list[tuple[float, float]] = []
    kinds: list[str] = []
    for j in mates:
        jx, jy = pts[j]
        distance = math.hypot(jx - bx, jy - by)
        max_range = 25.0 if mode == "throw" else 60.0
        if distance < 3.0 or distance > max_range:
            continue
        if mode == "kickoff" and jx > bx:
            continue
        if eng.group[j] is PositionGroup.GK and distance > 30:
            continue  # no long back-passes to the keeper
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
        if mode in (None, "corner") and bx > 78 and abs(by - MID_Y) > 12 and \
                jx > LENGTH - 17 and abs(jy - MID_Y) < 14:
            receivers.append(j)
            points.append((jx, jy))
            kinds.append("cross")
    if mode == "corner":
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
    length = np.maximum(np.linalg.norm(delta, axis=1), 1e-6)
    to_keeper = np.array([eng.group[j] is PositionGroup.GK for j in receivers])
    lofted = (np.array([k == "cross" for k in kinds]) | (length > 32)) & ~to_keeper
    unit = delta / length[:, None]
    ground_speed = np.clip(10 + 0.35 * length, 12, 26)
    flight = np.clip(0.9 + length / 25, 1.1, 2.8)
    speed = np.where(lofted, length / flight, ground_speed)
    rel = opp_pts[None, :, :] - ball[None, None, :]
    along = np.einsum("pkd,pd->pk", rel, unit)
    perp = np.linalg.norm(rel - along[..., None] * unit[:, None, :], axis=2)
    t_ball = np.maximum(along, 0) / speed[:, None]
    t_opp = np.maximum(perp - 1.0, 0) / 6.5 + 0.35
    valid = (along > 1.0) & (along < length[:, None] + 1.5)
    risk = np.where(valid, _sigmoid((t_ball - t_opp) * 4.0), 0.0)
    landing = along > length[:, None] - 4.0
    risk = np.where(lofted[:, None] & ~landing, risk * 0.25, risk)
    p_lane = np.prod(1 - 0.82 * risk, axis=1)
    marker = np.linalg.norm(target[:, None, :] - opp_pts[None, :, :], axis=2).min(axis=1) \
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
    recv_gap = np.linalg.norm(recv_pts - target, axis=1)
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
    if fast:
        utility += 0.002 * forward / 10
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
        utility = 0.005 + 0.12 * pressure**2 * loss
        options.append((utility, "clearance", PassOption(-1, clear_to, True, 0.3)))
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
        step /= max(np.linalg.norm(step), 1e-6)
        probe = ball + step * 4.0
        blocker = float(np.min(np.linalg.norm(opp_pts - probe, axis=1))) if len(opp_pts) else 20.0
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
    spread = 0.015 + 0.09 * (1 - skill / 100) + 0.06 * pressure + 0.03 * fatigue
    angle_error = eng.rng.normal(0, spread)
    length_error = eng.rng.normal(1.0, 0.07 * (1.2 - skill / 100))
    angle = math.atan2(ty - by, tx - bx) + angle_error
    reach = distance * length_error
    ax, ay = bx + math.cos(angle) * reach, by + math.sin(angle) * reach
    aim = np.array(eng.to_pitch(team, ax, ay))
    direction = aim - eng.ball
    direction /= max(float(np.linalg.norm(direction)), 1e-6)
    if lofted:
        flight = float(np.clip(0.9 + reach / 25, 1.1, 2.8))
        eng.ball_v = direction * reach / flight
        eng.ball_vz = 9.81 * flight / 2
        eng.ball_z = 0.1
    else:
        arrive = 5.0
        eng.ball_v = direction * math.sqrt(arrive**2 + 2 * 4.0 * reach)
        eng.ball_vz = 0.0
        eng.ball_z = 0.0
    eng.owner = -1
    eng.state = "pass"
    eng.last_touch = i
    eng.carry_target = None
    eng.pass_info = PassInfo(i, j, (float(aim[0]), float(aim[1])), lofted, kind, tried={i},
                             estimate=estimate)
    if kind != "clearance":
        eng.stats[team].passes += 1
        eng.lines[eng.players[i].player_id].passes += 1
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
    if eng.pass_info is not None and eng.pass_info.kind == "throw":
        return
    if rx > offside_line(opp_pts, ball_x) + 0.3 and rx > ball_x and rx > 52.5:
        eng.stats[team].offsides += 1
        eng._announce("offside", team, f"Offside: {eng.players[j].player.name}")
        eng._set_restart("free_kick", 1 - team, (float(eng.pos[j, 0]), float(eng.pos[j, 1])), 3.0)


def resolve_loose_or_pass(eng: "MatchEngine") -> None:
    info = eng.pass_info
    if info is not None and info.kind == "cross" and _aerial(eng, info):
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
        speed = float(np.linalg.norm(eng.ball_v))
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
                    base = 0.97 if c == info.receiver else 0.85
                    p = base * (0.9 + 0.1 * eng.a(c, "first_touch") / 100)
                    p *= 1 - max(0.0, speed - 15) / 30
                else:
                    p = (0.18 + 0.4 * eng.a(c, "interceptions") / 100
                         + 0.1 * eng.a(c, "anticipation") / 100) * closeness
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
    if eng.state == "pass" and float(np.linalg.norm(eng.ball_v)) < 1.0 and eng.ball_z <= 0:
        eng.state = "loose"
        eng.stopped_pass = (info, eng.t) if info is not None else None
        eng.pass_info = None


def _path_distance(eng: "MatchEngine") -> np.ndarray:
    """Each player's distance to the ball's path during the last tick, so a fast ball can't
    skip past a player between two ticks."""
    start, end = eng.prev_ball, eng.ball
    seg = end - start
    length_sq = float(seg @ seg)
    if length_sq < 1e-9:
        result: np.ndarray = np.linalg.norm(eng.pos - end, axis=1)
        return result
    t = np.clip(((eng.pos - start) @ seg) / length_sq, 0, 1)
    closest = start + t[:, None] * seg[None, :]
    result = np.linalg.norm(eng.pos - closest, axis=1)
    return result


def _take(eng: "MatchEngine", c: int, info: PassInfo | None) -> None:
    team = int(eng.team_of[c])
    if info is None and eng.stopped_pass is not None:
        # A pass that ran out of pace, gathered a moment later by its own side, still counts.
        stopped, when = eng.stopped_pass
        eng.stopped_pass = None
        if eng.t - when < 3.0 and int(eng.team_of[stopped.passer]) == team:
            info = stopped
    if isinstance(info, PassInfo):
        passer_team = int(eng.team_of[info.passer])
        if passer_team == team and info.kind != "clearance":
            eng.stats[team].passes_completed += 1
            eng.lines[eng.players[info.passer].player_id].passes_completed += 1
            eng.last_completed_pass = (info.passer, c, eng.t)
        elif passer_team != team:
            eng.lines[eng.players[c].player_id].interceptions += 1
            eng.commentate(team, f"{eng.players[c].player.short_name} reads it and intercepts")
    gain_possession(eng, c)


def _aerial(eng: "MatchEngine", info: PassInfo) -> bool:
    """A cross arriving in the box: keeper claim, then a heading duel."""
    landing = np.array(info.target)
    if float(np.linalg.norm(eng.ball - landing)) > 2.5 or eng.ball_z > 2.8:
        return False
    team = int(eng.team_of[info.passer])
    keeper = eng.keeper(1 - team)
    dx, _ = eng.to_att(1 - team, float(eng.ball[0]), float(eng.ball[1]))
    if keeper is not None and dx < 7 and float(np.linalg.norm(eng.pos[keeper] - eng.ball)) < 5:
        claim = 0.3 + 0.45 * eng.a(keeper, "gk_command_of_area") / 100
        if eng.rng.random() < claim:
            eng._announce("claim", 1 - team, f"{eng.players[keeper].player.name} claims the cross")
            gain_possession(eng, keeper, delay=2.0)
            return True
    near = np.flatnonzero(eng.active & (np.linalg.norm(eng.pos - eng.ball, axis=1) < 3.0))
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
    if best_a is not None and (best_d is None or eng.rng.random() < float(
            _sigmoid((aerial(best_a) - aerial(best_d)) / 8))):
        eng.pass_info = None
        eng.last_completed_pass = (info.passer, best_a, eng.t)
        eng.stats[team].passes_completed += 1
        eng.lines[eng.players[info.passer].player_id].passes_completed += 1
        eng.ball_z = 0.0
        eng.owner = best_a
        start_shot(eng, best_a, header=True)
        return True
    assert best_d is not None
    _clear(eng, best_d)
    return True


def _clear(eng: "MatchEngine", k: int) -> None:
    team = int(eng.team_of[k])
    angle = float(eng.rng.normal(0, 0.7))
    direction = np.array([math.cos(angle) * eng.attack_dir[team], math.sin(angle)])
    eng.ball_v = direction * float(eng.rng.uniform(13, 20))
    eng.ball_vz = float(eng.rng.uniform(3, 7))
    eng.ball_z = 1.0
    eng.owner = -1
    eng.state = "loose"
    eng.pass_info = None
    eng.last_touch = k
    eng.lines[eng.players[k].player_id].interceptions += 1


# --- tackles and fouls -----------------------------------------------------------------


def _tackles(eng: "MatchEngine", i: int) -> bool:
    team = int(eng.team_of[i])
    opps = eng.team_indices(1 - team)
    if len(opps) == 0:
        return False
    gaps = np.linalg.norm(eng.pos[opps] - eng.pos[i], axis=1)
    speed = float(np.linalg.norm(eng.vel[i]))
    heading = eng.vel[i] / speed if speed > 0.5 else None
    for k, gap in zip(opps.tolist(), gaps.tolist(), strict=True):
        if gap > TACKLE_RADIUS or eng.t < eng.tackle_ready[k] or eng.group[k] is PositionGroup.GK:
            continue
        # A defender standing in the carrier's path forces a duel straight away: players
        # can't run through each other.
        blocking = heading is not None and float((eng.pos[k] - eng.pos[i]) @ heading) > 0.35 * gap
        pressing = eng.instructions[1 - team].get("pressing", "normal")
        eagerness = {"low": 0.8, "normal": 1.0, "high": 1.25}.get(pressing, 1.0)
        chance = 0.4 if blocking else 0.12 * (0.6 + eng.a(k, "aggression") / 250) * eagerness
        if eng.rng.random() > chance:
            continue
        eng.tackle_ready[k] = eng.t + 1.3
        sliding = gap > 1.2
        tackle = (0.55 * eng.a(k, "sliding_tackle" if sliding else "standing_tackle")
                  + 0.25 * eng.a(k, "def_positioning") + 0.2 * eng.a(k, "strength"))
        own_x, _ = eng.to_att(1 - team, float(eng.pos[i, 0]), float(eng.pos[i, 1]))
        if own_x < 35:
            tackle += 6.0  # near their own goal defenders commit, with cover behind them
        dribble = (0.45 * eng.a(i, "dribbling") + 0.2 * eng.a(i, "agility")
                   + 0.15 * eng.a(i, "balance") + 0.2 * eng.a(i, "strength"))
        foul_chance = 0.035 * (eng.a(k, "aggression") / 70) * (1.4 if sliding else 1.0)
        dx, dy = eng.to_att(1 - team, float(eng.pos[i, 0]), float(eng.pos[i, 1]))
        if in_own_box(dx, dy):
            foul_chance *= 0.15  # defenders are careful in their own box
        if eng.rng.random() < foul_chance:
            _foul(eng, k, i)
            return True
        if eng.rng.random() < float(_sigmoid((tackle - dribble) / 12 + 0.15)):
            eng.lines[eng.players[k].player_id].tackles += 1
            eng.commentate(1 - team, f"{eng.players[k].player.short_name} wins it with a tackle "
                                     f"on {eng.players[i].player.short_name}")
            own_x, _ = eng.to_att(1 - team, float(eng.ball[0]), float(eng.ball[1]))
            keeps = 0.75 if own_x < 35 else 0.6  # defenders make sure of it near their goal
            if eng.rng.random() < keeps:
                gain_possession(eng, k)
            else:
                # Poked away, mostly up the pitch from the tackler's point of view.
                eng.owner = -1
                eng.state = "loose"
                angle = float(eng.rng.normal(0, 1.0))
                direction = np.array([math.cos(angle) * eng.attack_dir[1 - team], math.sin(angle)])
                eng.ball_v = direction * float(eng.rng.uniform(4, 10))
                eng.last_touch = k
            return True
        eng.tackle_ready[k] = eng.t + 1.8  # beaten: wrong-footed, needs a moment to recover
        eng.vel[k] *= 0.2
        eng.commentate(team, f"{eng.players[i].player.short_name} skips past "
                             f"{eng.players[k].player.short_name}")
    return False


def _foul(eng: "MatchEngine", fouler: int, victim: int) -> None:
    team = int(eng.team_of[fouler])
    name = eng.players[fouler].player.name
    eng.stats[team].fouls += 1
    eng._announce("foul", team, f"Foul by {name}")
    club = eng.sheets[team].club_id
    pid = eng.players[fouler].player_id
    roll = eng.rng.random()
    if roll < 0.006:
        eng.send_off(fouler, "straight red")
    elif roll < 0.006 + 0.12 + 0.1 * (eng.a(fouler, "aggression") > 80):
        eng.yellows[fouler] += 1
        eng.lines[pid].yellow += 1
        eng.stats[team].yellow += 1
        eng.events.append(MatchEvent(eng.minute, "yellow", club, pid))
        eng._announce("yellow", team, f"Yellow card: {name}")
        if eng.yellows[fouler] >= 2:
            eng.send_off(fouler, "second yellow")
    if eng.rng.random() < 0.012:
        _injure(eng, victim)
    victim_team = 1 - team
    vx, vy = eng.to_att(victim_team, float(eng.pos[victim, 0]), float(eng.pos[victim, 1]))
    if in_box(vx, vy):
        spot = eng.to_pitch(victim_team, PENALTY_SPOT, MID_Y)
        eng._announce("penalty", victim_team, "PENALTY!")
        eng._set_restart("penalty", victim_team, spot, 6.0)
    else:
        eng._set_restart("free_kick", victim_team,
                         (float(eng.pos[victim, 0]), float(eng.pos[victim, 1])), 3.5)


def _injure(eng: "MatchEngine", i: int) -> None:
    kind = int(eng.rng.choice(len(INJURIES), p=np.array(INJURY_WEIGHTS) / sum(INJURY_WEIGHTS)))
    name, median, spread = INJURIES[kind]
    days = max(1, int(round(median * math.exp(eng.rng.normal(0, spread)))))
    team = int(eng.team_of[i])
    sp = eng.players[i]
    eng.injuries.append(Injury(sp.player_id, eng.sheets[team].club_id, days, name))
    eng.events.append(MatchEvent(eng.minute, "injury", eng.sheets[team].club_id, sp.player_id,
                                 detail=name))
    eng._announce("injury", team, f"{sp.player.name} is injured ({name})")
    eng.stamina[i] = min(float(eng.stamina[i]), 0.2)  # the AI will take him off


# --- shots -----------------------------------------------------------------------------


def start_shot(eng: "MatchEngine", i: int, header: bool = False, penalty: bool = False,
               free_kick: bool = False) -> None:
    team = int(eng.team_of[i])
    bx, by = eng.to_att(team, float(eng.ball[0]), float(eng.ball[1]))
    distance = math.hypot(LENGTH - bx, MID_Y - by)
    opps = eng.team_indices(1 - team)
    opp_pts = eng.att_points(team, eng.pos[opps])
    nearest = (float(np.min(np.linalg.norm(opp_pts - np.array([bx, by]), axis=1)))
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
    speed = 22.0 if penalty else (13.0 if header else 17.0 + 13.0 * eng.a(i, "shot_power") / 100)
    aim = np.array(eng.to_pitch(team, LENGTH + 0.5, ty))
    direction = aim - eng.ball
    travel = max(float(np.linalg.norm(direction)), 0.5)
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
        eng.target[keeper] = aim
    elif outcome == "blocked":
        resolve = float(eng.rng.uniform(min(1.5, travel / 2), max(min(8.0, travel), 1.5)))
    eng.owner = -1
    eng.state = "shot"
    eng.last_touch = i
    eng.carry_target = None
    eng.shot_info = ShotInfo(i, outcome, xg, keeper, resolve, header=header, penalty=penalty)
    line = eng.lines[eng.players[i].player_id]
    line.shots += 1
    eng.stats[team].shots += 1
    eng.stats[team].xg += xg
    if outcome in ("goal", "saved"):
        line.shots_on_target += 1
        eng.stats[team].shots_on_target += 1
    name = eng.players[i].player.name
    what = "heads" if header else "shoots"
    if penalty:
        eng._announce("shot", team, f"{name} steps up...")
    else:
        eng._announce("shot", team, f"{name} {what} from {distance:.0f} m")


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
        blocker = int(blockers[np.argmin(np.linalg.norm(eng.pos[blockers] - eng.ball, axis=1))])
        roll = eng.rng.random()
        if roll < 0.45:  # the blocker gets it away
            eng._announce("block", 1 - team, f"Blocked by {eng.players[blocker].player.name}")
            _clear(eng, blocker)
        elif roll < 0.75:  # deflected behind
            eng._announce("block", 1 - team, "Blocked, out for a corner")
            eng.stats[team].corners += 1
            line_x = LENGTH if eng.attack_dir[team] > 0 else 0.0
            corner_y = 0.0 if float(eng.ball[1]) < MID_Y else 68.0
            eng._set_restart("corner", team, (line_x, corner_y), 5.0)
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
        eng._announce("save", 1 - team, f"Saved by {kname}")
        eng.pos[keeper] = eng.ball
        gain_possession(eng, keeper, delay=float(eng.rng.uniform(2.5, 4.5)))
        return
    eng.last_touch = keeper
    if eng.rng.random() < 0.3:
        eng._announce("save", 1 - team, f"{kname} tips it behind for a corner!")
        eng.stats[team].corners += 1
        line_x = LENGTH if eng.attack_dir[team] > 0 else 0.0
        corner_y = 0.0 if float(eng.ball[1]) < MID_Y else 68.0
        eng._set_restart("corner", team, (line_x, corner_y), 5.0)
        return
    eng._announce("save", 1 - team, f"{kname} parries it away!")
    back = -eng.attack_dir[team]  # away from the goal being attacked
    side = 1.0 if float(eng.ball[1]) >= MID_Y else -1.0  # keepers push shots wide
    eng.ball_v = np.array([back * float(eng.rng.uniform(3, 8)),
                           side * float(eng.rng.uniform(8, 15))])
    eng.ball_vz = float(eng.rng.uniform(0.5, 3))
    eng.state = "loose"


# --- restarts --------------------------------------------------------------------------


def pick_taker(eng: "MatchEngine", restart: Restart) -> int | None:
    idx = [int(i) for i in eng.team_indices(restart.team)]
    if not idx:
        return None
    outfield = [i for i in idx if eng.group[i] is not PositionGroup.GK] or idx
    spot = np.array(restart.spot)
    if restart.kind == "goal_kick":
        keeper = eng.keeper(restart.team)
        return keeper if keeper is not None else outfield[0]
    if restart.kind == "penalty":
        return max(outfield, key=lambda i: eng.a(i, "penalties"))
    if restart.kind == "corner":
        crossers = [i for i in outfield if eng.group[i] not in (PositionGroup.CB, PositionGroup.ST)]
        return max(crossers or outfield, key=lambda i: eng.a(i, "crossing"))
    if restart.kind == "kickoff":
        forwards = [i for i in outfield if eng.group[i] in (PositionGroup.ST, PositionGroup.AM)]
        return min(forwards or outfield, key=lambda i: float(np.linalg.norm(eng.pos[i] - spot)))
    if restart.kind == "free_kick":
        sx, sy = eng.to_att(restart.team, *restart.spot)
        if sx > 76 and abs(sy - MID_Y) < 18:
            return max(outfield, key=lambda i: eng.a(i, "free_kicks"))
    return min(outfield, key=lambda i: float(np.linalg.norm(eng.pos[i] - spot)))


def take_restart(eng: "MatchEngine", restart: Restart, taker: int) -> None:
    eng.ball = np.array(restart.spot, dtype=float)
    gain_possession(eng, taker, delay=0.0)
    kind = restart.kind
    if kind == "penalty":
        start_shot(eng, taker, penalty=True)
    elif kind == "kickoff":
        decide(eng, taker, mode="kickoff")
    elif kind == "throw_in":
        decide(eng, taker, mode="throw")
    elif kind == "corner":
        decide(eng, taker, mode="corner")
    elif kind == "goal_kick":
        decide(eng, taker, mode="goal_kick")
    elif kind == "free_kick":
        sx, sy = eng.to_att(restart.team, *restart.spot)
        if sx > 76 and abs(sy - MID_Y) < 18 and eng.rng.random() < 0.55:
            start_shot(eng, taker, free_kick=True)
        else:
            decide(eng, taker, mode="free_kick")
    if eng.owner == taker and eng.state == "owned" and kind != "free_kick":
        # Nothing on: just play it to the nearest teammate.
        mates = [int(j) for j in eng.team_indices(restart.team) if j != taker]
        if mates:
            j = min(mates, key=lambda m: float(np.linalg.norm(eng.pos[m] - eng.pos[taker])))
            target = eng.to_att(restart.team, float(eng.pos[j, 0]), float(eng.pos[j, 1]))
            start_pass(eng, taker, j, target, False, "throw" if kind == "throw_in" else "pass")


# --- substitutions and ratings ---------------------------------------------------------


def ai_substitutions(eng: "MatchEngine", team: int) -> None:
    if eng.subs_used[team] >= MAX_SUBS or not eng.bench[team]:
        return
    tired = sorted((int(i) for i in eng.team_indices(team)
                    if eng.group[i] is not PositionGroup.GK and eng.stamina[i] < 0.62
                    and i != eng.owner),
                   key=lambda i: float(eng.stamina[i]))
    for i in tired[:2]:
        if eng.subs_used[team] >= MAX_SUBS or not eng.bench[team]:
            return
        same = [sp for sp in eng.bench[team] if sp.group is eng.group[i]]
        pool = same or [sp for sp in eng.bench[team] if sp.group is not PositionGroup.GK]
        if not pool:
            return
        incoming = max(pool, key=lambda sp: sp.rating)
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
            rating = 6.0 + 0.3 * result + 1.0 * line.goals + 0.6 * line.assists
            rating += 0.12 * line.shots_on_target + 0.07 * (line.tackles + line.interceptions)
            if line.passes >= 10:
                rating += (line.passes_completed / line.passes - 0.78) * 2.5
            if group in (PositionGroup.GK, PositionGroup.CB, PositionGroup.FB):
                rating += 0.5 if conceded == 0 else -0.15 * conceded
            if group is PositionGroup.GK:
                rating += 0.2 * min(line.saves, 6) - 0.15 * conceded
            rating -= 0.3 * line.yellow + 1.5 * line.red
            if line.minutes < 20:
                rating = 6.0 + (rating - 6.0) * 0.4
            line.rating = round(float(np.clip(rating, 3.5, 10.0)), 1)
