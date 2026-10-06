"""Dead-ball restarts: from the ball going out (or the whistle) to the kick, throw or kick-off
that restarts play.

A restart moves through three stages:
  out     the ball has just gone out or play has stopped; it stays where it is for a moment
  setup   the ball is placed; players walk or jog to their restart positions (set_pieces.py)
          and the taker goes to the ball
  taken   once the setup time has passed and the players needed are in place (or at the
          latest at ``max_setup``), the taker plays it and live play resumes
Nobody is teleported: a late taker is replaced by whoever gets there first, and players who
are still on their way arrive late. Setup times, and how game management stretches them,
come from data/config/match/restarts.yaml. Substitutions wait for a restart.
"""

from typing import TYPE_CHECKING

import numpy as np

from footsim.defs.positions import PositionGroup
from footsim.match.engine import actions
from footsim.match.engine.pitch import LENGTH, MID_Y, WIDTH, in_box, norm
from footsim.match.engine.state import TAKER_REACH, Restart

if TYPE_CHECKING:
    from footsim.match.engine.engine import MatchEngine


def award(eng: "MatchEngine", kind: str, team: int, spot: tuple[float, float],
          variant: str | None = None) -> None:
    p = eng.defs.restarts
    variant = variant or _variant(eng, kind, team, spot)
    timing = p.timing[variant]
    setup = float(eng.rng.uniform(*timing.setup))
    factor = _game_management(eng, team, variant)
    if factor > 1:  # the referee adds some of the time wasted
        eng.clock.ledger.add("time_wasting", setup * (factor - 1) * p.time_wasting_allowance)
    setup *= factor
    out = 0.0 if variant in ("kickoff", "quick_free_kick") else p.ball_out
    eng.owner = -1
    eng.state = "dead"
    eng.pass_info = None
    eng.shot_info = None
    eng.ball_v[:] = 0
    eng.ball_z = 0.0
    eng.ball_vz = 0.0
    placed = out == 0
    if placed:
        eng.ball = np.array(spot, dtype=float)
    else:  # the ball stays where it went out, just off the pitch, until it's fetched
        eng.ball = np.array([min(max(float(eng.ball[0]), -1.5), LENGTH + 1.5),
                             min(max(float(eng.ball[1]), -1.5), WIDTH + 1.5)])
    restart = Restart(kind, team, spot, eng.t + out + setup, variant=variant,
                      awarded_at=eng.t, deadline=eng.t + out + timing.max_setup * factor,
                      placed=placed)
    eng.restart = restart
    restart.taker = pick_taker(eng, restart)
    eng.restart_awarded_at = eng.t
    eng.apply_pending_subs()
    eng.emit("restart", team, at=spot, kind=kind, variant=variant)


def _variant(eng: "MatchEngine", kind: str, team: int, spot: tuple[float, float]) -> str:
    p = eng.defs.restarts
    x, y = eng.to_att(team, *spot)
    if kind == "throw_in" and x > LENGTH - p.long_throw_range:
        strong = [i for i in eng.team_indices(team) if eng.group[i] is not PositionGroup.GK
                  and eng.a(int(i), "strength") >= p.long_throw_strength]
        if strong and eng.rng.random() < 0.5:
            return "long_throw"
    if kind == "free_kick":
        if x >= LENGTH - 35 and abs(y - MID_Y) <= 25:
            return "dangerous_free_kick"
        if x < LENGTH - 45 and eng.rng.random() < p.quick_free_kick_chance:
            return "quick_free_kick"
    if kind == "kickoff":
        return "kickoff_after_goal"  # a half's first kick-off passes its variant explicitly
    return kind


def _game_management(eng: "MatchEngine", team: int, variant: str) -> float:
    """Late on, the side ahead takes its time over its restarts and the side behind hurries."""
    p = eng.defs.restarts
    if eng.minute < p.late_minute or variant in ("kickoff", "penalty"):
        return 1.0
    lead = eng.score[team] - eng.score[1 - team]
    if lead > 0:
        return p.time_wasting
    if lead < 0:
        return p.hurry
    return 1.0


def pick_taker(eng: "MatchEngine", restart: Restart) -> int | None:
    idx = [int(i) for i in eng.team_indices(restart.team)]
    if not idx:
        return None
    outfield = [i for i in idx if eng.group[i] is not PositionGroup.GK] or idx
    spot = np.array(restart.spot)

    def nearest(pool: list[int]) -> int:
        return min(pool, key=lambda i: float(norm(eng.pos[i] - spot)))

    if restart.kind == "goal_kick":
        keeper = eng.keeper(restart.team)
        return keeper if keeper is not None else outfield[0]
    if restart.kind == "penalty":
        return max(outfield, key=lambda i: eng.a(i, "penalties"))
    if restart.kind == "corner":
        crossers = [i for i in outfield if eng.group[i] not in (PositionGroup.CB, PositionGroup.ST)]
        return max(crossers or outfield, key=lambda i: eng.a(i, "crossing"))
    if restart.variant == "long_throw":
        return max(outfield, key=lambda i: eng.a(i, "strength"))
    if restart.kind == "kickoff":
        forwards = [i for i in outfield if eng.group[i] in (PositionGroup.ST, PositionGroup.AM)]
        return nearest(forwards or outfield)
    if restart.variant == "dangerous_free_kick":
        return max(outfield, key=lambda i: eng.a(i, "free_kicks"))
    return nearest(outfield)


def tick(eng: "MatchEngine") -> None:
    restart = eng.restart
    assert restart is not None
    if not restart.placed:
        if eng.t < restart.awarded_at + eng.defs.restarts.ball_out:
            return
        eng.ball = np.array(restart.spot, dtype=float)
        restart.placed = True
    taker = restart.taker
    if taker is None or not eng.active[taker]:
        restart.taker = taker = pick_taker(eng, restart)
    if taker is None or eng.t < restart.ready_at:
        return
    spot = np.array(restart.spot)
    if float(norm(eng.pos[taker] - spot)) > TAKER_REACH:
        if eng.t >= restart.deadline:
            # The chosen taker is still on his way: whoever is closest takes it instead.
            closest = min((int(i) for i in eng.team_indices(restart.team)),
                          key=lambda i: float(norm(eng.pos[i] - spot)))
            restart.taker = closest
        return
    if eng.t < restart.deadline and not _ready(eng, restart):
        return
    eng.restart = None
    corner = restart.variant in ("corner", "long_throw")
    eng.emit("restart_taken", restart.team, taker, kind=restart.kind, variant=restart.variant,
             wait=round(eng.t - restart.awarded_at, 1), teleported=False,
             box_attackers=box_count(eng, restart.team, restart.team, taker) if corner else None,
             box_defenders=box_count(eng, 1 - restart.team, restart.team, None)
             if corner else None)
    take(eng, restart, taker)


def _ready(eng: "MatchEngine", restart: Restart) -> bool:
    if restart.variant in ("corner", "long_throw"):
        wanted = eng.defs.restarts.min_corner_attackers
        return box_count(eng, restart.team, restart.team, restart.taker) >= wanted
    return True


def box_count(eng: "MatchEngine", team: int, frame_team: int, skip: int | None) -> int:
    """Players of ``team`` inside the penalty area that ``frame_team`` attacks."""
    count = 0
    for i in eng.team_indices(team):
        if int(i) == skip:
            continue
        if in_box(*eng.to_att(frame_team, float(eng.pos[i, 0]), float(eng.pos[i, 1]))):
            count += 1
    return count


def take(eng: "MatchEngine", restart: Restart, taker: int) -> None:
    eng.ball = np.array(restart.spot, dtype=float)
    actions.gain_possession(eng, taker, delay=0.0, how=restart.kind)
    eng.taking_restart = restart.kind
    try:
        _play(eng, restart, taker)
    finally:
        eng.taking_restart = None


def _play(eng: "MatchEngine", restart: Restart, taker: int) -> None:
    kind = restart.kind
    if kind == "penalty":
        actions.start_shot(eng, taker, penalty=True)
    elif kind == "kickoff":
        actions.decide(eng, taker, mode="kickoff")
    elif restart.variant == "long_throw":
        actions.decide(eng, taker, mode="long_throw")
    elif kind == "throw_in":
        actions.decide(eng, taker, mode="throw")
    elif kind == "corner":
        actions.decide(eng, taker, mode="corner")
    elif kind == "goal_kick":
        actions.decide(eng, taker, mode="goal_kick")
    elif kind == "free_kick":
        sx, sy = eng.to_att(restart.team, *restart.spot)
        if (restart.variant == "dangerous_free_kick" and sx > 76 and abs(sy - MID_Y) < 18
                and eng.rng.random() < 0.55):
            actions.start_shot(eng, taker, free_kick=True)
        else:
            actions.decide(eng, taker, mode="free_kick")
    if eng.owner == taker and eng.state == "owned" and kind != "free_kick":
        # Nothing on: just play it to the nearest teammate.
        mates = [int(j) for j in eng.team_indices(restart.team) if j != taker]
        if mates:
            j = min(mates, key=lambda m: float(norm(eng.pos[m] - eng.pos[taker])))
            target = eng.to_att(restart.team, float(eng.pos[j, 0]), float(eng.pos[j, 1]))
            actions.start_pass(eng, taker, j, target, False,
                               "throw" if kind == "throw_in" else "pass")
