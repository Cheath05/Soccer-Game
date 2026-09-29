"""A saved shot is one the keeper can reach: it's placed inside his dive, so a catch never
snaps the ball into his hands from out of reach, and a keeper with no shot on target within
reach is beaten instead."""

import numpy as np
import pytest

from footsim.core.rng import derive_rng
from footsim.match.engine.actions import KEEPER_DIVE, _save_window
from footsim.match.engine.engine import MatchEngine
from footsim.match.engine.pitch import GOAL_HALF, LENGTH, MID_Y
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import World, get_world

SHOOTER = 0  # the home side shoots; the away keeper defends


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def _keeper_at(world: World, x: float, y: float) -> tuple[MatchEngine, int]:
    """An engine with the defending keeper at (x, y) in the shooting side's attacking frame."""
    home = synthetic_sheet(world.defs, world.picker, 1, 70)
    away = synthetic_sheet(world.defs, world.picker, 2, 70)
    engine = MatchEngine(world.defs, home, away, derive_rng(1, "saves"), record=False)
    keeper = engine.keeper(1 - SHOOTER)
    assert keeper is not None
    engine.pos[keeper] = np.array(engine.to_pitch(SHOOTER, x, y))
    return engine, keeper


def test_a_central_keeper_covers_the_middle_of_his_goal(world: World) -> None:
    engine, keeper = _keeper_at(world, LENGTH - 1.0, MID_Y)
    window = _save_window(engine, SHOOTER, keeper, LENGTH - 16.5, MID_Y)
    assert window is not None
    low, high = window
    assert low == pytest.approx(2 * MID_Y - high)  # centred on him
    assert high - low < 2 * GOAL_HALF  # but he can't reach the corners
    assert high - MID_Y == pytest.approx(KEEPER_DIVE * 17.0 / 15.5)  # his dive, projected


def test_the_window_follows_the_keeper_and_stops_at_the_posts(world: World) -> None:
    engine, keeper = _keeper_at(world, LENGTH - 1.5, MID_Y + 2.0)
    window = _save_window(engine, SHOOTER, keeper, LENGTH - 18.0, MID_Y)
    assert window is not None
    low, high = window
    assert low > MID_Y - GOAL_HALF + 0.3  # the far corner is out of his reach
    assert high == pytest.approx(MID_Y + GOAL_HALF - 0.3)  # the near post is covered


def test_a_keeper_out_of_position_cant_save(world: World) -> None:
    engine, keeper = _keeper_at(world, LENGTH - 20.0, MID_Y)  # rushed out: rounded
    assert _save_window(engine, SHOOTER, keeper, LENGTH - 12.0, MID_Y) is None
    engine, keeper = _keeper_at(world, LENGTH - 2.0, MID_Y + 12.0)  # stranded wide
    assert _save_window(engine, SHOOTER, keeper, LENGTH - 12.0, MID_Y - 5.0) is None
