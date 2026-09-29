"""Where players go while a restart is being set up.

During a dead ball each player walks or jogs to a target for that kind of restart: attackers
into the box for a corner, options around a throw-in, centre-backs splitting for a short goal
kick, a wall for a free kick near goal. Nobody is teleported: a player who is still on his
way when the kick is taken simply arrives late. The distances in the Laws are respected:
2 m at a throw-in, 9.15 m at corners and free kicks, and opponents outside the penalty area
at a goal kick (IFAB Laws 13, 15, 16, 17).

All coordinates here are in the team's attacking frame (x from its own goal line, 0, to the
opponent's, 105), like the rest of behaviours.py.
"""

from typing import TYPE_CHECKING

import numpy as np

from footsim.defs.positions import PositionGroup
from footsim.match.engine.pitch import BOX_DEPTH, BOX_HALF, LENGTH, MID_X, MID_Y, WIDTH, norm

if TYPE_CHECKING:
    from footsim.match.engine.engine import MatchEngine

KICK_DISTANCE = 9.15  # opponents at corners, free kicks and kick-offs
THROW_DISTANCE = 2.0
Array = np.ndarray


def arrange(eng: "MatchEngine", team: int, idx: np.ndarray, targets: Array,
            attacking: bool) -> None:
    """Replace ``targets`` (one row per player index in ``idx``) with restart positions."""
    restart = eng.restart
    assert restart is not None
    spot = np.array(eng.to_att(team, *restart.spot))
    variant = restart.variant
    outfield = [k for k, i in enumerate(idx)
                if eng.group[i] is not PositionGroup.GK and i != restart.taker]
    if variant in ("kickoff", "kickoff_after_goal"):
        _kickoff(eng, team, targets, outfield, attacking)
    elif variant == "penalty":
        _penalty(targets, outfield, attacking)
    elif variant in ("corner", "long_throw"):
        if attacking:
            _box_attack(eng, idx, targets, outfield, spot, eng.defs.restarts.corner_attackers)
        else:
            _box_defence(eng, team, idx, targets, outfield, spot)
    elif variant == "throw_in":
        _throw_in(eng, team, idx, targets, outfield, spot, attacking)
    elif variant == "goal_kick":
        _goal_kick(eng, team, idx, targets, outfield, attacking)
    elif variant == "dangerous_free_kick":
        if attacking:
            count = 4 if abs(spot[1] - MID_Y) < 14 else eng.defs.restarts.corner_attackers
            _box_attack(eng, idx, targets, outfield, spot, count)
        else:
            _wall_and_box(eng, team, idx, targets, outfield, spot)
    # Everyone else keeps their shape; the opponents keep their distance.
    if not attacking:
        _keep_distance(targets, outfield, spot, variant)
    targets[:, 0] = np.clip(targets[:, 0], 0.5, LENGTH - 0.5)
    targets[:, 1] = np.clip(targets[:, 1], 0.5, WIDTH - 0.5)


def _heading(eng: "MatchEngine", i: int) -> float:
    height = eng.players[i].player.height_cm
    return (eng.a(i, "heading_accuracy") + eng.a(i, "jumping") + 0.5 * eng.a(i, "strength")
            + 0.8 * (height - 180))


def _kickoff(eng: "MatchEngine", team: int, targets: Array, outfield: list[int],
             attacking: bool) -> None:
    targets[:, 0] = np.minimum(targets[:, 0], MID_X - 1.0)
    if not attacking:  # outside the centre circle until the ball is kicked
        centre = np.array([MID_X, MID_Y])
        for k in outfield:
            gap = targets[k] - centre
            distance = float(norm(gap))
            if distance < KICK_DISTANCE + 0.5:
                direction = gap / distance if distance > 1e-6 else np.array([-1.0, 0.0])
                targets[k] = centre + direction * (KICK_DISTANCE + 0.5)
                targets[k, 0] = min(targets[k, 0], MID_X - 1.0)


def _penalty(targets: Array, outfield: list[int], attacking: bool) -> None:
    for k in outfield:
        if attacking:  # outside the box and arc, ready for a rebound
            targets[k, 0] = min(targets[k, 0], LENGTH - BOX_DEPTH - 1.5)
        else:
            targets[k, 0] = max(targets[k, 0], BOX_DEPTH + 1.5)


def _box_attack(eng: "MatchEngine", idx: np.ndarray, targets: Array, outfield: list[int],
                spot: Array, count: int) -> None:
    """Corner, long throw or wide free kick: the best headers attack the box, a couple of
    players stay back in case of a counter."""
    side = 1.0 if spot[1] > MID_Y else -1.0  # the side the ball comes in from
    spots = [
        (100.8, MID_Y + side * 4.2),   # near post
        (100.8, MID_Y - side * 4.5),   # far post
        (102.3, MID_Y + side * 0.8),   # in front of the keeper
        (94.0, MID_Y - side * 1.5),    # penalty spot
        (97.0, MID_Y - side * 8.0),    # back post, deep
        (87.5, MID_Y - side * 3.0),    # edge of the box, for second balls
    ]
    ranked = sorted(outfield, key=lambda k: -_heading(eng, int(idx[k])))
    attackers = ranked[:count]
    rest = ranked[count:]
    for k, target in zip(attackers, spots, strict=False):
        targets[k] = target
    # The least useful in the air stay back; one sits at the edge of the box if there's room.
    by_pace = sorted(rest, key=lambda k: -eng.a(int(idx[k]), "sprint_speed"))
    backs = [(MID_X + 2, MID_Y - side * 10), (MID_X + 2, MID_Y + side * 10), (70.0, MID_Y)]
    for k, target in zip(by_pace, backs, strict=False):
        targets[k] = target
    for k in by_pace[len(backs):]:
        targets[k] = (86.0, MID_Y + side * 6)


def _box_defence(eng: "MatchEngine", team: int, idx: np.ndarray, targets: Array,
                 outfield: list[int], spot: Array) -> None:
    """Mixed marking: zones on the six-yard line and penalty spot, the best headers marking
    the most dangerous attackers, one outlet left upfield for the counter."""
    side = 1.0 if spot[1] > MID_Y else -1.0
    zones = [
        (1.5, MID_Y + side * 3.0),    # near post
        (5.5, MID_Y + side * 2.5),    # six-yard line, near
        (5.5, MID_Y - side * 1.0),    # six-yard line, middle
        (6.0, MID_Y - side * 4.5),    # six-yard line, far
        (10.5, MID_Y),                # penalty spot
    ]
    ranked = sorted(outfield, key=lambda k: -_heading(eng, int(idx[k])))
    forwards = [k for k in outfield
                if eng.group[int(idx[k])] in (PositionGroup.ST, PositionGroup.W)]
    outlet = max(forwards, key=lambda k: eng.a(int(idx[k]), "sprint_speed"), default=None)
    defenders = [k for k in ranked if k != outlet]
    zonal = defenders[:len(zones)]
    markers = defenders[len(zones):]
    for k, target in zip(zonal, zones, strict=False):
        targets[k] = target
    # Man-markers take the attackers in the box, goal-side.
    opponents = eng.team_indices(1 - team)
    threats = [int(j) for j in opponents
               if eng.group[int(j)] is not PositionGroup.GK]
    threat_pts = eng.att_points(team, eng.pos[threats]) if threats else np.zeros((0, 2))
    in_box = [p for p in threat_pts if p[0] <= BOX_DEPTH + 2 and abs(p[1] - MID_Y) <= BOX_HALF]
    in_box.sort(key=lambda p: float(np.hypot(p[0], p[1] - MID_Y)))
    for k, target in zip(markers, in_box, strict=False):
        targets[k] = (max(1.0, target[0] - 1.0), target[1])
    for k in markers[len(in_box):]:
        targets[k] = (16.5, MID_Y - side * 5)  # edge of the box
    if outlet is not None:
        targets[outlet] = (36.0, MID_Y + side * 8)


def _throw_in(eng: "MatchEngine", team: int, idx: np.ndarray, targets: Array,
              outfield: list[int], spot: Array, attacking: bool) -> None:
    toward = 1.0 if spot[1] > MID_Y else -1.0  # towards the touchline the ball went out of
    if attacking:
        options = [(spot[0] + 10.0, spot[1] - toward * 4.0),    # up the line
                   (spot[0] - 9.0, spot[1] - toward * 5.0),     # back down the line
                   (spot[0] + 1.0, spot[1] - toward * 13.0)]    # infield
        nearest = sorted(outfield, key=lambda k: float(norm(
            eng.att_points(team, eng.pos[[int(idx[k])]])[0] - spot)))
        for k, target in zip(nearest, options, strict=False):
            targets[k] = target
    else:
        # The nearest defenders pick up the options, goal-side.
        rivals = [int(j) for j in eng.team_indices(1 - team)
                  if eng.group[int(j)] is not PositionGroup.GK]
        rival_pts = eng.att_points(team, eng.pos[rivals]) if rivals else np.zeros((0, 2))
        close = sorted(rival_pts.tolist(), key=lambda p: float(np.hypot(*(np.array(p) - spot))))
        nearest = sorted(outfield, key=lambda k: float(norm(targets[k] - spot)))
        for k, point in zip(nearest[:3], close[:3], strict=False):
            targets[k] = (point[0] - 1.5, point[1])


def _goal_kick(eng: "MatchEngine", team: int, idx: np.ndarray, targets: Array,
               outfield: list[int], attacking: bool) -> None:
    ins = eng.instructions[team]
    if attacking:
        short = ins.get("passing") != "direct"
        centre_backs = [k for k in outfield if eng.group[int(idx[k])] is PositionGroup.CB]
        full_backs = [k for k in outfield if eng.group[int(idx[k])] is PositionGroup.FB]
        pivots = [k for k in outfield if eng.group[int(idx[k])] is PositionGroup.DM] or [
            k for k in outfield if eng.group[int(idx[k])] is PositionGroup.CM]
        if short:
            for k, y in zip(sorted(centre_backs, key=lambda k: targets[k, 1]),
                            (MID_Y - 14.0, MID_Y + 14.0), strict=False):
                targets[k] = (7.0, y)
            for k in full_backs:
                targets[k] = (21.0, 5.0 if targets[k, 1] < MID_Y else WIDTH - 5.0)
            if pivots:
                targets[pivots[0]] = (19.0, MID_Y)
        else:
            for k in outfield:
                if k not in centre_backs:
                    targets[k, 0] = min(targets[k, 0] + 16.0, 72.0)
    else:
        # Outside the penalty area until the ball is in play; a pressing side waits on its edge.
        press = ins.get("pressing") == "high"
        edge = LENGTH - BOX_DEPTH - 0.8
        for k in outfield:
            x, y = targets[k]
            if x > edge and abs(y - MID_Y) < BOX_HALF + 1:
                targets[k, 0] = edge
        if press:
            forwards = [k for k in outfield
                        if eng.group[int(idx[k])] in (PositionGroup.ST, PositionGroup.W,
                                                      PositionGroup.AM)]
            for k, y in zip(forwards, (MID_Y - 12, MID_Y + 12, MID_Y), strict=False):
                targets[k] = (edge, y)


def _wall_and_box(eng: "MatchEngine", team: int, idx: np.ndarray, targets: Array,
                  outfield: list[int], spot: Array) -> None:
    """A free kick near our goal: a wall on the line to goal, the rest guarding the box."""
    goal = np.array([0.0, MID_Y])
    to_goal = goal - spot
    distance = float(norm(to_goal))
    central = abs(spot[1] - MID_Y) < 20
    size = (4 if distance < 24 else 3 if distance < 30 else 2) if central else 1
    direction = to_goal / max(distance, 1e-6)
    across = np.array([-direction[1], direction[0]])
    wall_centre = spot + direction * KICK_DISTANCE
    # The tallest guard the box; the wall is made of the others.
    by_height = sorted(outfield, key=lambda k: -eng.players[int(idx[k])].player.height_cm)
    wall = by_height[-size:]
    for n, k in enumerate(wall):
        offset = (n - (size - 1) / 2) * 0.7
        targets[k] = wall_centre + across * offset
    guards = [k for k in outfield if k not in wall]
    line = max(8.0, min(14.0, spot[0] - 6.0))
    zones = [(line, MID_Y - 8), (line, MID_Y - 3), (line, MID_Y + 3), (line, MID_Y + 8),
             (line - 3, MID_Y), (line + 4, MID_Y - 12), (line + 4, MID_Y + 12)]
    for k, target in zip(guards, zones, strict=False):
        targets[k] = target


def _keep_distance(targets: Array, outfield: list[int], spot: Array, variant: str) -> None:
    """Opponents keep the distance the Laws require from the ball."""
    radius = {"throw_in": THROW_DISTANCE, "long_throw": THROW_DISTANCE,
              "corner": KICK_DISTANCE, "free_kick": KICK_DISTANCE,
              "dangerous_free_kick": KICK_DISTANCE - 0.01, "offside": KICK_DISTANCE,
              "penalty": KICK_DISTANCE}.get(variant)
    if radius is None:
        return
    for k in outfield:
        gap = targets[k] - spot
        distance = float(norm(gap))
        if distance < radius:
            direction = gap / distance if distance > 1e-6 else np.array([-1.0, 0.0])
            targets[k] = spot + direction * radius
