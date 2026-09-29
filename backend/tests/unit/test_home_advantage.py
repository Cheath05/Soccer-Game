"""Home advantage comes from the referee and the crowd (home_advantage.yaml), never from
ability, and a neutral venue has none of it."""

from dataclasses import replace

import pytest

from footsim.core.rng import derive_rng
from footsim.defs.match import HomeAdvantageDef
from footsim.match.engine.engine import MatchEngine
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import World, get_world

TICKS = 6000  # ten minutes


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def _engine(world: World, neutral: bool = False, defs: object = None) -> MatchEngine:
    home = synthetic_sheet(world.defs, world.picker, 1, 70)
    away = synthetic_sheet(world.defs, world.picker, 2, 70, formation="4-2-3-1")
    return MatchEngine(defs or world.defs, home, away,  # type: ignore[arg-type]
                       derive_rng(7, "home_advantage"), record=False, neutral=neutral)


def _state(engine: MatchEngine) -> tuple[object, ...]:
    return (engine.score, engine.pos.tobytes(), engine.ball.tobytes(),
            [(s.shots, s.passes, s.passes_completed, s.fouls) for s in engine.stats])


def test_the_gap_is_split_between_the_sides(world: World) -> None:
    engine = _engine(world)
    assert engine.venue_bias(0, 0.2) == pytest.approx(0.9)  # home: a little less
    assert engine.venue_bias(1, 0.2) == pytest.approx(1.1)  # away: a little more
    neutral = _engine(world, neutral=True)
    assert neutral.venue_bias(0, 0.2) == neutral.venue_bias(1, 0.2) == 1.0


def test_a_neutral_venue_plays_like_no_home_advantage(world: World) -> None:
    zero = HomeAdvantageDef.model_validate(
        {"referee": {"foul": 0, "card": 0}, "crowd": {"decisions": 0, "execution": 0}})
    home_without = _engine(world, defs=replace(world.defs, home_advantage=zero))
    neutral = _engine(world, neutral=True)
    home = _engine(world)
    for engine in (home_without, neutral, home):
        engine.run(max_ticks=TICKS)
    assert _state(neutral) == _state(home_without)
    assert _state(home) != _state(neutral)  # the crowd and referee do change the match
