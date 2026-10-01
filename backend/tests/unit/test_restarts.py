"""Restarts: the right one is given, players set up without teleporting, the Laws' distances
are kept, and substitutions wait for a stoppage."""

import numpy as np
import pytest

from footsim.core.rng import derive_rng
from footsim.match.engine import behaviours, restarts
from footsim.match.engine.engine import DT, MatchEngine
from footsim.match.engine.pitch import BOX_DEPTH, BOX_HALF, LENGTH, MID_X, MID_Y, WIDTH
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import World, get_world


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def _engine(world: World, seed: int = 4) -> MatchEngine:
    home = synthetic_sheet(world.defs, world.picker, 1, 74)
    away = synthetic_sheet(world.defs, world.picker, 2, 72)
    return MatchEngine(world.defs, home, away, derive_rng(seed, "restarts"), record=False)


def _live(engine: MatchEngine) -> MatchEngine:
    """Play on until the ball is in play (the opening kick-off has been taken)."""
    while engine.restart is not None:
        engine.step()
    return engine


def _outfield(engine: MatchEngine, team: int) -> list[int]:
    keeper = engine.keeper(team)
    return [int(i) for i in engine.team_indices(team) if i != keeper]


# --- which restart --------------------------------------------------------------------------


def test_ball_barely_over_the_touchline_is_a_throw_in_to_the_other_side(world: World) -> None:
    engine = _live(_engine(world))
    engine.last_touch = _outfield(engine, 0)[3]
    engine._out_of_play(40.0, -0.05)
    assert engine.restart is not None
    assert (engine.restart.kind, engine.restart.team) == ("throw_in", 1)
    assert engine.restart.spot == (40.0, 0.0)


def test_goal_line_gives_goal_kick_or_corner_by_last_touch(world: World) -> None:
    engine = _live(_engine(world))
    assert engine.attack_dir[0] == 1  # home attacks towards x = 105 in the first half
    engine.last_touch = _outfield(engine, 0)[5]  # an attacker put it over
    engine._out_of_play(LENGTH + 0.1, 20.0)
    assert engine.restart is not None and engine.restart.kind == "goal_kick"
    assert engine.restart.team == 1 and engine.restart.spot[0] == pytest.approx(LENGTH - 5.5)

    engine = _live(_engine(world))
    engine.last_touch = _outfield(engine, 1)[2]  # a defender put it over his own line
    engine._out_of_play(LENGTH + 0.1, 60.0)
    assert engine.restart is not None and engine.restart.kind == "corner"
    assert engine.restart.team == 0 and engine.restart.spot == (LENGTH, WIDTH)
    assert engine.stats[0].corners == 1


# --- setting up -----------------------------------------------------------------------------


def _targets_after(engine: MatchEngine, kind: str, team: int, spot: tuple[float, float],
                   variant: str | None = None) -> np.ndarray:
    engine.award_restart(kind, team, spot, variant)
    behaviours.update_targets(engine)
    return engine.target.copy()


def test_opponents_keep_their_distance(world: World) -> None:
    corner = (LENGTH, 0.0)
    engine = _live(_engine(world))
    targets = _targets_after(engine, "corner", 0, corner)
    for i in _outfield(engine, 1):
        assert np.linalg.norm(targets[i] - np.array(corner)) >= 9.15 - 1e-6

    engine = _live(_engine(world))
    free_kick = (70.0, 30.0)
    targets = _targets_after(engine, "free_kick", 0, free_kick, "free_kick")
    for i in _outfield(engine, 1):
        assert np.linalg.norm(targets[i] - np.array(free_kick)) >= 9.15 - 1e-6

    engine = _live(_engine(world))
    throw = (50.0, WIDTH)
    targets = _targets_after(engine, "throw_in", 0, throw, "throw_in")
    for i in _outfield(engine, 1):
        assert np.linalg.norm(targets[i] - np.array(throw)) >= 2.0 - 1e-6


def test_goal_kick_opponents_stay_outside_the_box(world: World) -> None:
    engine = _live(_engine(world))
    targets = _targets_after(engine, "goal_kick", 1, (LENGTH - 5.5, MID_Y))
    for i in _outfield(engine, 0):  # home attacks this end: outside the box it defends
        x, y = targets[i]
        assert not (x > LENGTH - BOX_DEPTH and abs(y - MID_Y) < BOX_HALF)


def test_corner_brings_attackers_into_the_box(world: World) -> None:
    engine = _live(_engine(world))
    targets = _targets_after(engine, "corner", 0, (LENGTH, 0.0))
    in_box = sum(1 for i in _outfield(engine, 0)
                 if targets[i, 0] > LENGTH - BOX_DEPTH and abs(targets[i, 1] - MID_Y) < BOX_HALF)
    assert in_box >= world.defs.restarts.corner_attackers


def test_kickoff_opponents_stay_out_of_the_centre_circle(world: World) -> None:
    engine = _live(_engine(world))
    engine._kickoff(1, teleport=False, after_goal=True)
    targets = engine.target
    for i in _outfield(engine, 0):
        assert np.linalg.norm(targets[i] - np.array([MID_X, MID_Y])) >= 9.15 - 1e-6


def test_restarts_take_time_and_nobody_teleports(world: World) -> None:
    engine = _engine(world, seed=9)
    previous_pos = engine.pos.copy()
    previous_ids = [sp.player_id for sp in engine.players]
    previous_clock = engine.clock.elapsed
    for _ in range(12000):
        engine.step()
        ids = [sp.player_id for sp in engine.players]
        moved = np.linalg.norm(engine.pos - previous_pos, axis=1)
        caught = {e.player for e in engine.log if e.kind == "save" and e.t >= engine.t - DT - 1e-6}
        for i in range(22):
            if ids[i] != previous_ids[i] or not engine.active[i]:
                continue  # a substitute coming on, or a player sent off
            limit = engine.max_speed[i] * DT * 1.2 + 0.05 + (2.5 if i in caught else 0.0)
            assert moved[i] <= limit, f"player {i} jumped {moved[i]:.2f} m at t={engine.t:.1f}"
        assert engine.clock.elapsed - previous_clock == pytest.approx(DT)
        previous_pos, previous_ids = engine.pos.copy(), ids
        previous_clock = engine.clock.elapsed
    taken = [e for e in engine.log if e.kind == "restart_taken" and e.data["kind"] != "kickoff"]
    assert taken and all(not e.data["teleported"] for e in taken)
    waits = {e.data["variant"]: e.data["wait"] for e in taken}
    for variant, wait in waits.items():
        low = world.defs.restarts.timing[variant].setup[0]
        assert wait >= low * world.defs.restarts.hurry - 1e-6, variant
    corners = [e for e in taken if e.data["variant"] == "corner"]
    for e in corners:
        assert (e.data["box_attackers"] >= world.defs.restarts.min_corner_attackers
                or e.data["wait"] >= world.defs.restarts.timing["corner"].max_setup)


def test_a_taker_waits_on_the_ball_instead_of_running_past_it(world: World) -> None:
    """Play-test, 30 Sep: a taker sprinting at the spot ran past it and back until the restart
    was due, 6 to 19 turns a restart. Once he has reached the ball he stays on it."""
    engine = _engine(world, seed=9)
    current: tuple[object, int] | None = None
    arrived: float | None = None
    checked = 0
    for _ in range(12000):
        engine.step()
        restart = engine.restart
        if restart is None or not restart.placed or restart.taker is None:
            current, arrived = None, None
            continue
        i = restart.taker
        if current != (restart, i):  # a new restart, or a new taker for it
            current, arrived = (restart, i), None
        gap = float(np.linalg.norm(engine.pos[i] - np.array(restart.spot)))
        if arrived is None:
            if gap <= restarts.TAKER_REACH:
                arrived = engine.t
            continue
        if engine.t - arrived >= 1.0:
            checked += 1
            speed = float(np.linalg.norm(engine.vel[i]))
            assert gap <= restarts.TAKER_REACH, f"taker {i} {gap:.1f} m off at t={engine.t:.1f}"
            assert speed < 1.0, f"taker {i} moving at {speed:.1f} m/s at t={engine.t:.1f}"
    assert checked > 200


def test_substitution_waits_for_a_stoppage(world: World) -> None:
    engine = _live(_engine(world))
    assert engine.restart is None and not engine.ball_dead
    out = engine.players[_outfield(engine, 0)[4]].player_id
    on = engine.bench[0][0].player_id
    engine.substitute(0, out, on)
    assert engine.pending_for(0) == [(out, on)] and engine.subs_used[0] == 1
    assert out in [sp.player_id for sp in engine.players]
    with pytest.raises(ValueError):
        engine.substitute(0, out, engine.bench[0][1].player_id)  # already waiting
    engine.award_restart("throw_in", 1, (30.0, 0.0))
    ids = [sp.player_id for sp in engine.players]
    assert on in ids and out not in ids and engine.pending_for(0) == []
    assert engine.subs_used[0] == 1


def test_a_substitute_starts_unbooked(world: World) -> None:
    # A booking belongs to the player, not his slot: the man coming on starts with no yellow
    # and can tackle at once, while the outgoing player keeps his card on his own line.
    engine = _live(_engine(world))
    slot = _outfield(engine, 0)[4]
    out = engine.players[slot].player_id
    engine.yellows[slot] = 1
    engine.lines[out].yellow = 1
    engine.tackle_ready[slot] = engine.t + 5.0
    on = engine.bench[0][0].player_id
    engine.substitute(0, out, on)
    engine.award_restart("throw_in", 1, (30.0, 0.0))
    assert engine.players[slot].player_id == on
    assert engine.yellows[slot] == 0 and engine.tackle_ready[slot] == 0.0
    assert engine.lines[out].yellow == 1


def test_a_substitute_sizes_up_duels_afresh(world: World) -> None:
    # Duel state is kept by player index, so the newcomer must not inherit the outgoing
    # player's engagements or take-on cooldowns (he'd skip sizing up a duel). Others keep theirs.
    engine = _live(_engine(world))
    slot, rival = _outfield(engine, 0)[4], _outfield(engine, 1)[4]
    other, carrier = _outfield(engine, 1)[5], _outfield(engine, 0)[5]
    engine.engaged[slot] = (rival, engine.t)
    engine.engaged[rival] = (slot, engine.t)
    engine.engaged[other] = (carrier, engine.t)
    engine.take_on_ready[(slot, rival)] = engine.take_on_ready[(rival, slot)] = engine.t + 5.0
    engine.substitute(0, engine.players[slot].player_id, engine.bench[0][0].player_id)
    engine.award_restart("throw_in", 1, (30.0, 0.0))
    assert slot not in engine.engaged
    assert all(c != slot for c, _ in engine.engaged.values())
    assert not any(slot in pair for pair in engine.take_on_ready)
    assert engine.engaged[other][0] == carrier


def test_a_restart_taker_who_goes_off_is_replaced(world: World,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    # The taker is chosen when the restart is awarded. If his slot is substituted before he
    # takes it, the choice is made again among the players now on the pitch.
    from footsim.match.engine import restarts
    engine = _live(_engine(world))
    engine.award_restart("throw_in", 0, (30.0, 0.0))
    assert engine.restart is not None and engine.ball_dead
    slot, keep, other = (_outfield(engine, 0)[k] for k in (4, 6, 7))
    engine.restart.taker = slot
    monkeypatch.setattr(restarts, "pick_taker", lambda eng, restart: keep)
    engine.substitute(0, engine.players[slot].player_id, engine.bench[0][0].player_id)
    assert engine.restart.taker == keep
    # Substituting anyone else leaves the taker alone.
    monkeypatch.setattr(restarts, "pick_taker", lambda eng, restart: -1)
    engine.substitute(0, engine.players[other].player_id, engine.bench[0][0].player_id)
    assert engine.restart.taker == keep
