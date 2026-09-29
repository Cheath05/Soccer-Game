"""A match is fully determined by its inputs and seed: repeating it, or stepping it in
different batch sizes (as the live viewer does at different speeds), changes nothing."""

import numpy as np
import pytest

from footsim.core.rng import derive_rng
from footsim.match.engine.engine import MatchEngine
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import World, get_world

TICKS = 6000  # ten minutes of play


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def _engine(world: World, seed: int = 3) -> MatchEngine:
    home = synthetic_sheet(world.defs, world.picker, 1, 70)
    away = synthetic_sheet(world.defs, world.picker, 2, 70, formation="4-2-3-1")
    return MatchEngine(world.defs, home, away, derive_rng(seed, "determinism"), record=False)


def _state(engine: MatchEngine) -> tuple[object, ...]:
    return (engine.score, engine.tick_count, engine.pos.tobytes(), engine.ball.tobytes(),
            [(s.shots, s.passes, s.passes_completed, s.fouls) for s in engine.stats],
            [(f["type"], f["t"]) for f in engine.feed])


def test_same_seed_same_match(world: World) -> None:
    first, second = _engine(world), _engine(world)
    first.run(max_ticks=TICKS)
    second.run(max_ticks=TICKS)
    assert _state(first) == _state(second)


def test_step_batching_does_not_change_the_match(world: World) -> None:
    whole, stepped = _engine(world), _engine(world)
    whole.run(max_ticks=TICKS)
    rng = np.random.default_rng(0)
    done = 0
    while done < TICKS:  # uneven batches, like a viewer changing speed
        batch = min(int(rng.integers(1, 700)), TICKS - done)
        stepped.run(max_ticks=batch)
        done += batch
    assert _state(whole) == _state(stepped)


def test_recording_frames_does_not_change_the_match(world: World) -> None:
    headless, watched = _engine(world), _engine(world)
    watched.record = True
    headless.run(max_ticks=TICKS)
    watched.run(max_ticks=TICKS)
    assert _state(headless) == _state(watched)


def test_different_seeds_differ(world: World) -> None:
    first, second = _engine(world, seed=3), _engine(world, seed=4)
    first.run(max_ticks=TICKS)
    second.run(max_ticks=TICKS)
    assert _state(first) != _state(second)


def test_a_runner_holding_the_line_stops_on_his_mark(world: World) -> None:
    """A sprinting forward runner eases off in time to stop on his target instead of
    overrunning it (overrunning the offside line gives the offside away)."""
    engine = _engine(world)
    runner = 9  # a home forward
    engine.pos[runner] = (40.0, 34.0)
    engine.vel[runner] = (8.0, 0.0)  # already at full tilt towards the line
    mark = np.array([60.0, 34.0])
    furthest = 0.0
    for _ in range(60):  # six seconds: time to arrive and settle
        engine.target[runner] = mark
        engine.urgent[runner] = engine.running[runner] = True
        engine._move_players()
        furthest = max(furthest, float(engine.pos[runner, 0] - mark[0]))
    assert furthest < 0.5
    assert float(np.linalg.norm(engine.pos[runner] - mark)) < 0.3
