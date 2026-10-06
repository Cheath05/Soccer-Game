"""The defending side's shape (Phase D2): three lines placed from the ball."""

import pytest

from footsim.core.rng import derive_rng
from footsim.match.engine import behaviours
from footsim.match.engine.engine import MatchEngine
from footsim.match.synthetic import synthetic_sheet
from footsim.world.context import World, get_world


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


@pytest.fixture(scope="module")
def engine(world: World) -> MatchEngine:
    home = synthetic_sheet(world.defs, world.picker, 1, 70, formation="4-3-3")
    away = synthetic_sheet(world.defs, world.picker, 2, 70)
    return MatchEngine(world.defs, home, away, derive_rng(1, "shape"), record=False)


@pytest.mark.parametrize("ball", [12.0, 25.0, 35.0, 50.0])
def test_in_our_half_the_back_line_and_midfield_are_goal_side_of_the_ball(
        engine: MatchEngine, ball: float) -> None:
    back, mid, front = behaviours._defending_lines(engine, ball, 33.0, 30.0, False)
    assert back < mid <= ball  # both lines between the ball and our goal (in our own box the
                               # midfield is level with it, 6 m in front of the back line)
    assert front > ball       # the forwards stay upfield as an outlet
    assert front - back <= 30.0 + 1e-9


def test_the_lines_never_pass_the_instruction_and_a_high_press_lifts_them(
        engine: MatchEngine) -> None:
    back, mid, _ = behaviours._defending_lines(engine, 90.0, 33.0, 30.0, False)
    assert back == 33.0 and mid <= back + 15.0
    pressing, _, _ = behaviours._defending_lines(engine, 90.0, 33.0, 30.0, True)
    assert pressing == 37.0


def test_formation_x_maps_onto_the_lines(engine: MatchEngine) -> None:
    lines = (20.0, 30.0, 42.0)
    assert behaviours._line_x(behaviours.X_BACK, *lines) == pytest.approx(20.0)
    assert behaviours._line_x(behaviours.X_MID, *lines) == pytest.approx(30.0)
    assert behaviours._line_x(behaviours.X_FRONT, *lines) == pytest.approx(42.0)
    holding = behaviours._line_x(0.30, *lines)
    assert 20.0 < holding < 30.0  # a holding midfielder screens between the lines


def test_wingers_drop_into_the_midfield_line_with_the_ball_in_our_half(
        engine: MatchEngine) -> None:
    engine.restart = None
    engine.owner = -1
    team = 0
    winger = next(i for i in engine.team_indices(team)
                  if engine.group[i].value == "W")
    midfielder = next(i for i in engine.team_indices(team)
                      if engine.group[i].value == "CM")
    engine.ball[:] = engine.to_pitch(team, 30.0, 34.0)  # 30 m from our goal
    engine.last_touch = int(engine.team_indices(1)[5])  # they have it
    behaviours.update_targets(engine)
    winger_x = engine.att_points(team, engine.target[[winger]])[0, 0]
    mid_x = engine.att_points(team, engine.target[[midfielder]])[0, 0]
    assert winger_x < 30.0 + 3.0 and abs(winger_x - mid_x) < 6.0
