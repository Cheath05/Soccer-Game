"""Attack against defence by rating (2.3f): a defender's own ratings decide how much he puts an
opponent off. Golden values can't show a response going the wrong way; these pin it."""

import numpy as np
import pytest

from footsim.core.rng import derive_rng
from footsim.domain.attributes import ATTR_INDEX
from footsim.match.engine import actions
from footsim.match.engine.engine import MatchEngine
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import World, get_world


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def _engine(world: World) -> MatchEngine:
    home = synthetic_sheet(world.defs, world.picker, 1, 70)
    away = synthetic_sheet(world.defs, world.picker, 2, 70)
    engine = MatchEngine(world.defs, home, away, derive_rng(1, "defending"), record=False)
    engine.pos[:] = (-50.0, -50.0)  # everyone far away unless placed
    return engine


def _set(engine: MatchEngine, i: int, **values: float) -> None:
    for name, value in values.items():
        engine.attr[i, ATTR_INDEX[name]] = value


def test_a_better_marker_puts_a_receiver_off_more(world: World) -> None:
    engine = _engine(world)
    receiver, marker = 9, 14
    engine.pos[receiver], engine.pos[marker] = (60.0, 34.0), (59.0, 34.0)
    _set(engine, marker, marking=40)
    loose = actions._touch_pressure(engine, receiver)
    _set(engine, marker, marking=85)
    assert actions._touch_pressure(engine, receiver) > loose > 0


def test_a_better_defender_puts_a_shooter_off_more(world: World) -> None:
    engine = _engine(world)
    shooter, defender = 9, 14
    engine.pos[shooter], engine.pos[defender] = (90.0, 34.0), (91.5, 34.5)
    bx, by = engine.to_att(0, 90.0, 34.0)
    _set(engine, defender, def_positioning=40, standing_tackle=40)
    weak = actions.shot_pressure(engine, shooter, 0, bx, by)
    _set(engine, defender, def_positioning=88, standing_tackle=88)
    assert actions.shot_pressure(engine, shooter, 0, bx, by) > weak > 0


def test_a_carrier_expects_less_against_a_better_tackler(world: World) -> None:
    engine = _engine(world)
    carrier, defender = 9, 14
    engine.pos[carrier], engine.pos[defender] = (60.0, 34.0), (64.5, 34.0)
    engine.ball, engine.owner = np.array([60.0, 34.0]), carrier
    ball = np.array(engine.to_att(0, 60.0, 34.0))
    opp_pts = engine.att_points(0, engine.pos[engine.team_indices(1)])

    def best_carry() -> float:
        options = actions._carry_options(engine, carrier, 0, ball, opp_pts, 0.0)
        return max(u for u, kind, payload in options
                   if kind == "carry" and payload.target != (float(ball[0]), float(ball[1])))

    _set(engine, defender, standing_tackle=40, def_positioning=40, strength=40)
    easy = best_carry()
    _set(engine, defender, standing_tackle=90, def_positioning=90, strength=90)
    assert best_carry() < easy
