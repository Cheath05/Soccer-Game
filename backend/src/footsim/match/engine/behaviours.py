"""Off-ball movement: where each player without the ball wants to be.

Every few ticks each team recomputes its players' targets:
  1. Formation anchors: the slot's base position plus the formation's and the role's
     offsets for the current phase, stretched between a back line and a front line that
     depend on the ball, the defensive-line instruction and the mentality.
  2. In possession: attackers respect the offside line, forwards with a taste for runs hold
     on the last defender's shoulder, and players near the ball move into open space.
  3. Out of possession: the nearest players press the ball (more of them with high
     pressing), the rest mark the nearest attacker goal-side, and the keeper sets his angle.
  4. Set pieces put players in their restart positions.
"""

from typing import TYPE_CHECKING

import numpy as np

from footsim.defs.formations import Phase
from footsim.defs.positions import PositionGroup
from footsim.defs.roles import RunType
from footsim.match.engine.pitch import BOX_DEPTH, BOX_HALF, LENGTH, MID_X, MID_Y, WIDTH

if TYPE_CHECKING:
    from footsim.match.engine.engine import MatchEngine

LINE_HEIGHT = {"deep": 24.0, "normal": 33.0, "high": 42.0}
BLOCK_SPAN = {"deep": 26.0, "normal": 30.0, "high": 34.0}
WIDTH_IN = {"narrow": 46.0, "normal": 54.0, "wide": 62.0}
MENTALITY_PUSH = {"defensive": -6.0, "balanced": 0.0, "attacking": 6.0}
PRESS = {"low": (7.0, 1), "normal": (13.0, 1), "high": (21.0, 2)}  # trigger m, pressers
DANGER_ZONE = 38.0  # ball this close to our goal line: always engage it
COUNTER_PRESS_SECONDS = 4.0
MARKING_GROUPS = {PositionGroup.CB, PositionGroup.FB, PositionGroup.DM, PositionGroup.CM}
MARKING_GROUPS_HIGH_PRESS = MARKING_GROUPS | {PositionGroup.AM, PositionGroup.W}
X_BACK, X_FRONT = 0.18, 0.70  # formation x of the back line and the strikers
CANDIDATE_ANGLES = np.linspace(0, 2 * np.pi, 8, endpoint=False)


def update_targets(eng: "MatchEngine") -> None:
    eng.urgent[:] = False
    eng.running[:] = False
    for team in (0, 1):
        _team(eng, team)
    if eng.restart is not None and eng.restart.taker is not None:
        eng.target[eng.restart.taker] = eng.restart.spot
        eng.urgent[eng.restart.taker] = True
    if eng.owner >= 0:
        eng.target[eng.owner] = eng.carry_target if eng.carry_target is not None else eng.pos[
            eng.owner]
        eng.urgent[eng.owner] = eng.carry_urgent


def _phase(ball_x: float, attacking: bool) -> Phase:
    if attacking:
        if ball_x < 35:
            return Phase.BUILD_UP
        return Phase.PROGRESSION if ball_x < 70 else Phase.FINAL_THIRD
    if ball_x > 60:
        return Phase.DEF_HIGH
    return Phase.DEF_MID if ball_x > 32 else Phase.DEF_LOW


def _team(eng: "MatchEngine", team: int) -> None:
    idx = eng.team_indices(team)
    if len(idx) == 0:
        return
    ins = eng.instructions[team]
    bx, by = eng.to_att(team, float(eng.ball[0]), float(eng.ball[1]))
    restart = eng.restart
    attacking = eng.possession_team() == team
    kickoff = restart is not None and restart.kind == "kickoff"
    phase = _phase(bx, attacking)
    slots = {s.id: s for s in eng.formation[team].slots}

    if attacking and not kickoff:
        push = MENTALITY_PUSH.get(ins.get("mentality", ""), 0.0)
        back = float(np.clip(bx - 32 + push, 14, 52))
        front = min(back + 42 + push * 0.5, 96.0)
        width = WIDTH_IN.get(ins.get("width", ""), 54.0)
        shift = 0.22
    else:
        line = LINE_HEIGHT.get(ins.get("line", ""), 33.0)
        back = float(np.clip(min(line, bx - 9), 6, line))
        if ins.get("pressing") == "high" and bx > 60 and not kickoff:
            back = line + 4
        front = back + BLOCK_SPAN.get(ins.get("line", ""), 30.0)
        width = 0.72 * WIDTH_IN.get(ins.get("width", ""), 54.0)
        shift = 0.42
        if kickoff:
            back, front = 22.0, 49.0
    stretch = (front - back) / (X_FRONT - X_BACK)

    targets = np.zeros((len(idx), 2))
    for k, i in enumerate(idx):
        slot = slots.get(eng.slot[i])
        xn, yn = (slot.base.x, slot.base.y) if slot else (0.4, 0.5)
        if slot and phase in slot.phase_offsets:
            xn += slot.phase_offsets[phase].dx
            yn += slot.phase_offsets[phase].dy
        role_offset = eng.role[i].movement.phase_offsets.get(phase)
        if role_offset is not None:
            side = 0.0 if abs(yn - 0.5) < 0.05 else (1.0 if yn > 0.5 else -1.0)
            xn += role_offset.dx
            yn += role_offset.d_out * side
        if eng.group[i] is PositionGroup.GK:
            targets[k] = _keeper_spot(bx, by, attacking and not kickoff, back)
            continue
        x = back + (xn - X_BACK) * stretch
        y = MID_Y + (yn - 0.5) * width + (by - MID_Y) * shift
        targets[k] = (x, y)

    targets[:, 0] = np.clip(targets[:, 0], 1.0, LENGTH - 1.0)
    targets[:, 1] = np.clip(targets[:, 1], 1.5, WIDTH - 1.5)
    if kickoff:
        targets[:, 0] = np.minimum(targets[:, 0], MID_X - 1.0)

    opp_pts = eng.att_points(team, eng.pos[eng.team_indices(1 - team)])
    if restart is not None and restart.kind in ("corner", "penalty"):
        _set_piece(eng, team, idx, targets, attacking)
    elif attacking and restart is None:
        _attack(eng, team, idx, targets, opp_pts, bx, by)
    elif not attacking:
        _defend(eng, team, idx, targets, opp_pts, bx, by, ins)

    pitch = eng.att_points(team, targets)
    for k, i in enumerate(idx):
        if i == eng.owner:
            continue
        if eng.pass_info is not None and eng.pass_info.receiver == i and eng.state == "pass":
            eng.target[i] = _meet_ball(eng, i)
            eng.urgent[i] = True
            continue
        eng.target[i] = pitch[k]
    if eng.state == "loose" and attacking:
        # Our loose ball: the nearest player goes to get it.
        chaser = min((int(i) for i in idx if eng.group[i] is not PositionGroup.GK),
                     key=lambda i: float(np.linalg.norm(eng.pos[i] - eng.ball)), default=None)
        if chaser is not None:
            eng.target[chaser] = eng.ball + eng.ball_v * 0.4
            eng.urgent[chaser] = True


def _meet_ball(eng: "MatchEngine", i: int) -> np.ndarray:
    """Where a pass receiver should go: into the ball's path, not just the aimed point."""
    info = eng.pass_info
    assert info is not None
    if info.lofted and eng.ball_z > 1.0:
        return np.array(info.target)
    speed = float(np.linalg.norm(eng.ball_v))
    if speed < 0.5:
        return eng.ball.copy()
    direction = eng.ball_v / speed
    stop = eng.ball + direction * speed**2 / (2 * 4.0)  # where the ball will come to rest
    segment = stop - eng.ball
    length_sq = max(float(segment @ segment), 1e-6)
    t = float(np.clip((eng.pos[i] - eng.ball) @ segment / length_sq, 0, 1))
    result: np.ndarray = eng.ball + t * segment
    return result


def _keeper_spot(bx: float, by: float, attacking: bool, back: float) -> tuple[float, float]:
    if attacking:
        return float(np.clip(back - 18, 4, 18)), MID_Y + (by - MID_Y) * 0.2
    dx, dy = bx, by - MID_Y
    distance = max(np.hypot(dx, dy), 1.0)
    depth = float(np.clip(1.5 + distance * 0.06, 1.0, 7.0))
    return depth * dx / distance + 0.5, MID_Y + depth * dy / distance


def offside_line(opp_pts: np.ndarray, ball_x: float) -> float:
    """x of the second-last opponent in the attacking frame (never inside our own half)."""
    if len(opp_pts) < 2:
        return LENGTH
    second_last = float(np.sort(opp_pts[:, 0])[-2])
    return max(second_last, ball_x, MID_X)


def _attack(eng: "MatchEngine", team: int, idx: np.ndarray, targets: np.ndarray,
            opp_pts: np.ndarray, bx: float, by: float) -> None:
    line = offside_line(opp_pts, bx)
    carrier = eng.owner if eng.owner >= 0 and int(eng.team_of[eng.owner]) == team else None
    for k, i in enumerate(idx):
        if eng.group[i] is PositionGroup.GK or i == carrier:
            continue
        runs = eng.role[i].movement.runs.get(RunType.IN_BEHIND, 0.0)
        if runs >= 0.3 and bx > 38 and carrier is not None:
            targets[k, 0] = line - 1.0
            eng.running[i] = True
            eng.urgent[i] = True
        targets[k, 0] = min(targets[k, 0], line - 1.0)

    # Players near the ball look for open space to receive in.
    if carrier is None or len(opp_pts) == 0:
        return
    ball = np.array([bx, by])
    near = [k for k, i in enumerate(idx) if i != carrier and eng.group[i] is not PositionGroup.GK
            and np.linalg.norm(targets[k] - ball) < 28 and not eng.running[i]]
    for k in near:
        i = idx[k]
        radius = 3.0 + eng.role[i].movement.freedom * 40
        candidates = targets[k] + radius * np.column_stack((np.cos(CANDIDATE_ANGLES),
                                                            np.sin(CANDIDATE_ANGLES)))
        candidates = np.vstack([targets[k], candidates])
        candidates[:, 0] = np.clip(candidates[:, 0], 2, min(line - 0.5, LENGTH - 2))
        candidates[:, 1] = np.clip(candidates[:, 1], 2, WIDTH - 2)
        gaps = np.linalg.norm(candidates[:, None, :] - opp_pts[None, :, :], axis=2).min(axis=1)
        lane = _lane_clearance(ball, candidates, opp_pts)
        drift = np.linalg.norm(candidates - targets[k], axis=1)
        score = np.minimum(gaps, 8.0) + 0.6 * np.minimum(lane, 5.0) - 0.25 * drift
        targets[k] = candidates[int(np.argmax(score))]


def _lane_clearance(ball: np.ndarray, points: np.ndarray, opp_pts: np.ndarray) -> np.ndarray:
    """Distance of the nearest opponent to each passing lane from the ball."""
    d = points - ball
    length = np.maximum(np.linalg.norm(d, axis=1), 1e-6)
    u = d / length[:, None]
    rel = opp_pts[None, :, :] - ball[None, None, :]
    s = np.clip(np.einsum("pkd,pd->pk", rel, u), 0, length[:, None])
    closest = ball[None, None, :] + s[..., None] * u[:, None, :]
    perp = np.linalg.norm(opp_pts[None, :, :] - closest, axis=2)
    result: np.ndarray = perp.min(axis=1)
    return result


def _defend(eng: "MatchEngine", team: int, idx: np.ndarray, targets: np.ndarray,
            opp_pts: np.ndarray, bx: float, by: float, ins: dict[str, str]) -> None:
    trigger, pressers = PRESS.get(ins.get("pressing", ""), (13.0, 1))
    ball = np.array([bx, by])
    own = eng.att_points(team, eng.pos[idx])
    loose = eng.owner < 0
    if loose:
        # Chase a loose ball (or a pass the other side just played) towards where it'll be.
        ahead = eng.ball + eng.ball_v * 0.5
        ball = np.array(eng.to_att(team, float(ahead[0]), float(ahead[1])))
        trigger, pressers = 30.0, 1
    danger = ball[0] < DANGER_ZONE and not loose
    if danger:  # near our goal the ball is always engaged, with a second man covering
        trigger, pressers = max(trigger, 20.0), max(pressers, 2)
    if eng.t - eng.turnover_at < COUNTER_PRESS_SECONDS and not loose:
        # We just lost it: the nearest players hunt the ball straight away.
        trigger, pressers = max(trigger, 18.0), max(pressers, 2)
    outfield = [k for k, i in enumerate(idx) if eng.group[i] is not PositionGroup.GK]
    distance = {k: float(np.linalg.norm(own[k] - ball)) for k in outfield}
    chasers = sorted(outfield, key=lambda k: distance[k])[:pressers]
    goal = np.array([0.0, MID_Y])
    to_goal = (goal - ball) / max(float(np.linalg.norm(goal - ball)), 1e-6)
    for rank, k in enumerate(chasers):
        if distance[k] <= trigger or (loose and rank == 0):
            if rank == 0:
                targets[k] = ball + to_goal * 1.2
            else:
                targets[k] = ball + to_goal * 5.0  # cover: block the route to goal
            eng.urgent[idx[k]] = True

    # Recovering players sprint: anyone well out of position, and everyone when the ball
    # is near our goal.
    recover_at = 3.0 if ball[0] < DANGER_ZONE else 9.0
    for k in outfield:
        if float(np.linalg.norm(own[k] - targets[k])) > recover_at:
            eng.urgent[idx[k]] = True

    # Everyone else marks the nearest attacker in his zone, goal-side.
    if len(opp_pts) == 0:
        return
    markers_from = MARKING_GROUPS_HIGH_PRESS if ins.get("pressing") == "high" else MARKING_GROUPS
    for k in outfield:
        if k in chasers and eng.urgent[idx[k]]:
            continue
        if eng.group[idx[k]] not in markers_from:
            continue  # forwards screen and press rather than man-mark
        gaps = np.linalg.norm(opp_pts - targets[k], axis=1)
        nearest = int(np.argmin(gaps))
        if gaps[nearest] < 12.0:
            mark = opp_pts[nearest] - np.array([1.8, 0.0])
            track = eng.role[idx[k]].defending.track_runners
            weight = 0.45 + 0.3 * track
            targets[k] = weight * mark + (1 - weight) * targets[k]
            if opp_pts[nearest, 0] < targets[k, 0] - 3:
                eng.urgent[idx[k]] = True  # an attacker is getting in behind: recover


def _set_piece(eng: "MatchEngine", team: int, idx: np.ndarray, targets: np.ndarray,
               attacking: bool) -> None:
    restart = eng.restart
    assert restart is not None
    outfield = [k for k, i in enumerate(idx) if eng.group[i] is not PositionGroup.GK
                and i != restart.taker]
    if restart.kind == "penalty":
        for k in outfield:
            if attacking:
                targets[k, 0] = min(targets[k, 0], LENGTH - BOX_DEPTH - 1.5)
            else:
                targets[k, 0] = max(targets[k, 0], BOX_DEPTH + 1.5)
        return
    # Corner: aerial threats attack the box; defenders pack it.
    heading = {k: eng.a(idx[k], "heading_accuracy") + eng.a(idx[k], "jumping") for k in outfield}
    ranked = sorted(outfield, key=lambda k: -heading[k])
    if attacking:
        spots = [(100.5, 30.5), (101.0, 38.5), (94.0, 34.0), (97.5, 26.0), (97.5, 42.0)]
        for k, spot in zip(ranked[:5], spots, strict=False):
            targets[k] = spot
        for k in ranked[5:]:
            targets[k] = (58.0, MID_Y + (targets[k, 1] - MID_Y) * 0.6)
    else:
        spots = [(2.5, 30.0), (2.5, 38.0), (5.0, 34.0), (6.0, 28.0), (6.0, 40.0), (9.0, 31.0),
                 (9.0, 37.0), (11.5, 34.0), (14.0, 28.0), (14.0, 40.0)]
        for k, spot in zip(ranked, spots, strict=False):
            targets[k] = spot
        if ranked:
            targets[ranked[-1]] = (35.0, MID_Y)  # an outlet for the counter
    for k in range(len(targets)):
        if abs(targets[k, 1] - MID_Y) > BOX_HALF + 8 and attacking:
            targets[k, 1] = MID_Y + np.sign(targets[k, 1] - MID_Y) * (BOX_HALF + 8)
