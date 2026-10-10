"""The football clock: display, added time and breaks."""

import pytest

from footsim.core.rng import derive_rng
from footsim.match.engine.clock import ClockState, MatchClock, event_label
from footsim.match.engine.engine import MatchEngine
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import World, get_world


def test_display_counts_minutes_and_seconds() -> None:
    clock = MatchClock(get_world().defs.clock)
    for elapsed, shown in ((3.0, "00:03"), (87.4, "01:27"), (764.0, "12:44"),
                           (2698.0, "44:58"), (2700.0, "45:00 +00:00"), (2797.0, "45:00 +01:37")):
        clock.elapsed = elapsed
        assert clock.display() == shown
    clock.start_period(2)
    clock.elapsed = 437.0
    assert clock.display() == "52:17"
    clock.elapsed = 2682.0
    assert clock.display() == "89:42"
    clock.elapsed = 2700.0
    assert clock.display() == "90:00 +00:00"


def test_labels_use_added_time_notation() -> None:
    assert event_label(1, 0) == "1'"
    assert event_label(1, 2699) == "45'"
    assert event_label(1, 2700) == "45+1'"
    assert event_label(1, 2821) == "45+3'"
    assert event_label(2, 0) == "46'"
    assert event_label(2, 2760) == "90+2'"
    assert event_label(3, 60) == "92'"


def test_added_time_follows_the_ledger_within_limits() -> None:
    quiet = MatchClock(get_world().defs.clock)
    assert quiet.announce() == 2  # only the base allowance
    busy = MatchClock(get_world().defs.clock)
    busy.start_period(2)
    for cause in ["goal"] * 3 + ["substitution"] * 8 + ["injury"] * 2:
        busy.ledger.add(cause)
    assert busy.announce() == 9  # capped
    busy.elapsed = busy.regulation + 9 * 60 - 1
    assert not busy.due_to_end()
    busy.elapsed += 1
    assert busy.due_to_end()


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def _engine(world: World, hold: bool) -> MatchEngine:
    home = synthetic_sheet(world.defs, world.picker, 1, 72)
    away = synthetic_sheet(world.defs, world.picker, 2, 72)
    engine = MatchEngine(world.defs, home, away, derive_rng(8, "clock"), record=False)
    engine.hold_at_breaks = hold
    return engine


def test_watched_match_waits_at_half_time_and_matches_headless(world: World) -> None:
    held = _engine(world, hold=True)
    held.run()
    assert held.at_break and held.clock.state is ClockState.BREAK and held.period == 1
    assert held.clock.announced is not None
    half_time_tick = held.tick_count
    held.run(max_ticks=100)  # nothing happens while waiting
    assert held.tick_count == half_time_tick
    held.start_next_period()
    assert held.period == 2 and held.clock.elapsed == 0 and not held.at_break
    held.run(max_ticks=6000)

    headless = _engine(world, hold=False)
    headless.run(max_ticks=half_time_tick + 6000)
    assert headless.tick_count == held.tick_count
    assert headless.score == held.score
    assert headless.pos.tobytes() == held.pos.tobytes()
    assert [(s.shots, s.passes) for s in headless.stats] == \
        [(s.shots, s.passes) for s in held.stats]


def test_changes_made_together_are_one_stoppage() -> None:
    """Play-test, 9 Oct: added time ran long. Two changes at one stoppage cost the referee one
    stoppage and a little more, not two."""
    world = get_world()
    eng = MatchEngine(world.defs, synthetic_sheet(world.defs, world.picker, 1, 72),
                      synthetic_sheet(world.defs, world.picker, 2, 72), derive_rng(5, "subs"),
                      record=False)
    while not (eng.ball_dead and eng.t > 60):
        eng.step()
    outfield = [eng.players[int(i)].player_id for i in eng.team_indices(0)
                if eng.position[int(i)] != "GK"]
    before = eng.clock.ledger.seconds
    eng.substitute(0, outfield[0], eng.bench[0][0].player_id)
    eng.substitute(0, outfield[1], eng.bench[0][0].player_id)
    allowance = world.defs.clock.allowance
    assert eng.clock.ledger.seconds - before == pytest.approx(
        allowance["substitution"] + allowance["substitution_extra"])
