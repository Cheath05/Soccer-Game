"""Pass resolution: how readily an opponent near a pass takes it."""

from dataclasses import replace
from typing import Any

import numpy as np
import pytest

from footsim.core.rng import derive_rng
from footsim.match.engine import actions
from footsim.match.engine.engine import MatchEngine
from footsim.match.engine.state import PassInfo
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import World, get_world


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


class _Rolls:
    """The engine's generator, except that every plain roll comes up ``value``."""

    def __init__(self, rng: np.random.Generator, value: float) -> None:
        self.rng, self.value = rng, value

    def random(self) -> float:
        return self.value

    def __getattr__(self, name: str) -> Any:
        return getattr(self.rng, name)


def _opponent_takes_it(world: World, scale: float) -> bool:
    """One opponent at the very edge of reach of a pass, on a roll of 0.03: only the floor
    of his chance can be high enough."""
    home = synthetic_sheet(world.defs, world.picker, 1, 70)
    away = synthetic_sheet(world.defs, world.picker, 2, 70)
    engine = MatchEngine(world.defs, home, away, derive_rng(1, "floor"), record=False)
    engine.defs = replace(engine.defs, passing=engine.defs.passing.model_copy(
        update={"intercept_scale": scale}))
    passer, receiver, opponent = 5, 8, 16
    engine.pos[:] = (-50.0, -50.0)  # everyone else far away
    engine.pos[passer], engine.pos[receiver] = (30.0, 34.0), (60.0, 34.0)
    engine.prev_ball, engine.ball = np.array([40.0, 34.0]), np.array([41.0, 34.0])
    engine.pos[opponent] = (41.0, 34.0 + actions.CONTROL_RADIUS * 0.9999)
    engine.ball_v, engine.ball_z = np.array([15.0, 0.0]), 0.0
    engine.owner, engine.state = -1, "pass"
    engine.pass_info = PassInfo(passer, receiver, (60.0, 34.0), False, "pass", tried={passer})
    engine.rng = _Rolls(engine.rng, 0.03)  # type: ignore[assignment]
    actions.resolve_loose_or_pass(engine)
    return engine.owner == opponent


def test_intercept_scale_covers_the_last_chance(world: World) -> None:
    # A 5% floor at scale 1.0 beats the roll; at 0.5 the floor is 2.5% and doesn't.
    assert _opponent_takes_it(world, 1.0)
    assert not _opponent_takes_it(world, 0.5)
