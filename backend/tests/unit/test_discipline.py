"""Fouls and cards in the agent engine (2.4): denying an obvious goal-scoring opportunity
(Law 12), a booked player's caution applied once, and engagements that lapse."""

import numpy as np
import pytest

from footsim.core.rng import derive_rng
from footsim.match.engine import duels
from footsim.match.engine.engine import MatchEngine
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import World, get_world


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def _engine(world: World, seed: int) -> MatchEngine:
    home = synthetic_sheet(world.defs, world.picker, 1, 70)
    away = synthetic_sheet(world.defs, world.picker, 2, 70)
    engine = MatchEngine(world.defs, home, away, derive_rng(seed, "discipline"), record=False)
    engine.pos[:] = (-50.0, -50.0)  # everyone far away unless placed
    keeper = engine.keeper(1)
    assert keeper is not None
    engine.pos[keeper] = (104.0, 34.0)
    return engine


def _foul(engine: MatchEngine, attacker: int, defender: int, at: tuple[float, float]) -> dict:
    engine.pos[attacker], engine.pos[defender] = at, (at[0] - 0.8, at[1] + 0.5)
    engine.ball, engine.owner = np.array(at), attacker
    before = len(engine.log)
    duels.commit_foul(engine, defender, attacker, source="tackle")
    event = next(e for e in engine.log[before:] if e.kind == "foul")
    return event.data


def test_denying_an_obvious_goal_chance_outside_the_area_is_a_red_card(world: World) -> None:
    engine = _engine(world, 1)
    data = _foul(engine, 9, 14, (80.0, 34.0))  # through on goal, 25 m out, nobody covering
    assert data["dogso"] and data["card"] == "red" and not engine.active[14]


def test_in_the_area_a_challenge_for_the_ball_is_a_caution_and_a_penalty(world: World) -> None:
    engine = _engine(world, 2)
    data = _foul(engine, 9, 14, (95.0, 34.0))
    assert data["dogso"] and data["penalty"] and data["card"] == "yellow"


def test_a_covering_defender_means_it_was_no_obvious_chance(world: World) -> None:
    engine = _engine(world, 3)
    engine.pos[15] = (90.0, 36.0)  # between him and the goal
    data = _foul(engine, 9, 14, (80.0, 34.0))
    assert not data["dogso"]


def test_a_lapsed_engagement_starts_again(world: World) -> None:
    """A defender who had let a carrier go sizes him up afresh when he meets him again,
    instead of carrying an old engagement over and tackling at once."""
    engine = _engine(world, 4)
    carrier, defender = 9, 14
    engine.pos[carrier], engine.pos[defender] = (60.0, 34.0), (61.0, 34.0)
    engine.ball, engine.owner = np.array([60.0, 34.0]), carrier
    engine.t = 100.0
    engine.engaged[defender] = (carrier, 10.0, 10.0)  # engaged long ago, then let go
    duels.contest(engine, carrier)
    assert engine.engaged[defender][1] == pytest.approx(100.0)  # since: now


def test_one_missed_tick_keeps_an_engagement_and_two_let_it_lapse(world: World) -> None:
    """Whatever the clock's rounding: on the engine's own clock, a defender who was not the
    nearest for one tick is still engaged, and one away for two ticks sizes the carrier up
    again. (At 2 ticks exactly, the test used to go either way about half the time.)"""
    engine = _engine(world, 5)
    carrier, defender = 9, 14
    engine.pos[carrier], engine.pos[defender] = (60.0, 34.0), (61.0, 34.0)
    engine.ball, engine.owner = np.array([60.0, 34.0]), carrier
    for start in range(200):
        engine.t = 0.0
        for _ in range(start):
            engine.t += duels.DT
        last = engine.t
        for missed, lapsed in ((1, False), (2, True)):
            engine.t = last
            for _ in range(missed + 1):
                engine.t += duels.DT
            engine.engaged[defender] = (carrier, -5.0, last)
            engine.tackle_ready[defender] = 0.0
            duels.contest(engine, carrier)
            since = engine.engaged[defender][1]
            assert (since == engine.t) is lapsed, (start, missed)
