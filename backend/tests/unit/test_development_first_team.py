"""Development rewards a place in the first team (people/development.py, development.yaml):
a substitute who is named but never comes on is credited a few minutes (the bench credit), which
count with the minutes he played towards a young player's growth; and an academy product aged 21
or younger who plays regularly has his potential raised a little every month, to a cap."""

import numpy as np
import pytest

from footsim.core.rng import derive_rng
from footsim.defs.development import DevelopmentDef
from footsim.defs.positions import PositionGroup
from footsim.match.engine.engine import MatchEngine
from footsim.match.synthetic import synthetic_sheet
from footsim.people.development import (
    DevelopmentInput,
    FloatArray,
    Traits,
    academy_boost,
    monthly_change,
)
from footsim.world.context import World, get_world


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def _quiet(world: World) -> DevelopmentDef:
    return world.defs.development.model_copy(update={"noise": 0.0})


def _traits(peak: float = 27.5, decline: float = 32.0) -> Traits:
    return Traits(peak_age=np.array([peak]), decline_age=np.array([decline]),
                  ceiling_bonus=np.array([0.0]), ageless=np.array([False]))


def _change(rules: DevelopmentDef, minutes: float, bench: float | None = None,
            age: float = 20.0, potential: float = 85.0, overall: float = 60.0) -> float:
    """One player's change in overall this month."""
    inp = DevelopmentInput(
        attrs=np.zeros((1, 1)), ages=np.array([age]), potential=np.array([potential]),
        groups=[PositionGroup.CM], minutes=np.array([minutes]),
        bench_minutes=None if bench is None else np.array([bench]))
    change = monthly_change(rules, inp, np.array([overall]), _traits(), np.random.default_rng(0))
    return float(change[0])


# --- the bench credit ---------------------------------------------------------------------


def test_bench_minutes_count_with_the_minutes_he_played(world: World) -> None:
    rules = _quiet(world)
    left_out = _change(rules, 0.0)
    on_the_bench = _change(rules, 0.0, bench=900.0)
    assert on_the_bench > left_out * 1.2  # a young player on the bench grows faster
    assert _change(rules, 0.0, bench=900.0) == _change(rules, 900.0)  # counted like minutes
    assert _change(rules, 0.0, bench=0.0) == left_out == _change(rules, 0.0, bench=None)
    # They add to the minutes he really played: 1,000 played and 400 on the bench cross into the
    # band of a player with 1,400 played.
    assert _change(rules, 1000.0, bench=400.0) == _change(rules, 1400.0)
    assert _change(rules, 1000.0, bench=400.0) > _change(rules, 1000.0)


def test_the_bench_is_worth_far_less_than_playing(world: World) -> None:
    rules = _quiet(world)
    a_season_on_the_bench = 46 * rules.bench_credit_minutes  # every league match, never used
    first, last = rules.minutes[0][0], rules.minutes[-1][0]
    assert first < a_season_on_the_bench < last  # out of the lowest band, short of the top ones
    assert (_change(rules, 0.0) < _change(rules, 0.0, bench=a_season_on_the_bench)
            < _change(rules, float(last)))


def test_bench_credit_changes_nothing_once_he_is_past_his_peak(world: World) -> None:
    rules = _quiet(world)
    assert _change(rules, 0.0, bench=900.0, age=30.0) == _change(rules, 0.0, age=30.0)


def test_both_engines_name_their_bench_in_the_report(world: World) -> None:
    """Results are recorded from the report, so each engine says who was named a substitute
    (the home side's, then the away side's), whether or not he came on: the credit goes to those
    who didn't (world/results.py credit_bench)."""
    home = synthetic_sheet(world.defs, world.picker, 1, 75)
    away = synthetic_sheet(world.defs, world.picker, 2, 72, formation="4-4-2")
    named = [sp.player_id for sheet in (home, away) for sp in sheet.bench]
    assert len(named) >= 14

    quick = world.quick.play(home, away, derive_rng(3, "bench"))
    assert quick.bench == named
    came_on = {pid for pid, line in quick.players.items() if not line.started}
    assert came_on and came_on <= set(named)  # a substitute who came on is in the lines too...
    unused = set(named) - came_on
    assert unused and unused.isdisjoint(quick.players)  # ...and one who didn't isn't

    engine = MatchEngine(world.defs, home, away, derive_rng(3, "bench"), record=False)
    engine.run(max_ticks=600)
    assert engine.report().bench == named  # the bench as named, not as it is left


# --- the academy boost --------------------------------------------------------------------


def _rules(world: World, **changes: float) -> DevelopmentDef:
    """The academy numbers pinned, so these tests don't move when the YAML is tuned."""
    pinned = {"academy_max_age": 21, "academy_regular_minutes": 1800,
              "academy_boost_per_year": 3.0, "academy_boost_cap": 8.0,
              "academy_potential_ceiling": 94, **changes}
    return world.defs.development.model_copy(update=pinned)


def _step(rules: DevelopmentDef, ages: list[float], minutes: list[float], academy: list[bool],
          potential: list[float], boost: list[float]) -> tuple[FloatArray, list[int]]:
    new, points = academy_boost(rules, np.array(ages), np.array(minutes),
                                np.array(academy, dtype=bool), np.array(potential),
                                np.array(boost))
    return new, [int(p) for p in points]


def test_only_academy_regulars_aged_21_or_younger_are_boosted(world: World) -> None:
    rules = _rules(world)
    new, points = _step(
        rules,
        ages=[19.5, 19.5, 19.5, 19.5, 21.9, 22.0, 25.0],
        minutes=[2000, 2000, 1799, 1800, 2000, 2000, 2000],
        academy=[True, False, True, True, True, True, True],
        potential=[80.0] * 7, boost=[0.0] * 7)
    month = 3.0 / 12
    #   regular, not an academy product, one minute short, exactly regular,
    #   21 in whole years, 22, 25
    assert new.tolist() == [month, 0.0, 0.0, month, month, 0.0, 0.0]
    assert points == [0] * 7  # a quarter of a point isn't a point yet


def test_fractions_carry_until_a_whole_point_reaches_his_potential(world: World) -> None:
    rules = _rules(world)
    potential, boost, gained = 80.0, 0.0, []
    for _ in range(12):  # three points a year, a quarter of one a month
        new, points = _step(rules, [19.0], [2500], [True], [potential], [boost])
        boost, potential = float(new[0]), potential + points[0]
        gained.append(points[0])
    assert gained == [0, 0, 0, 1] * 3
    assert (boost, potential) == (3.0, 83.0)


def test_a_third_of_a_point_a_month_still_adds_up_to_whole_points(world: World) -> None:
    """Four a year is 0.333... a month; three of them are a point, whatever the rounding."""
    rules = _rules(world, academy_boost_per_year=4.0)
    potential, boost, gained = 80.0, 0.0, []
    for _ in range(12):
        new, points = _step(rules, [19.0], [2500], [True], [potential], [boost])
        boost, potential = float(new[0]), potential + points[0]
        gained.append(points[0])
    assert gained == [0, 0, 1] * 4
    assert potential == 84.0


def test_the_boost_stops_at_the_cap(world: World) -> None:
    rules = _rules(world)
    potential, boost = 80.0, 0.0
    for _ in range(60):  # five years of starting every week
        new, points = _step(rules, [19.0], [2500], [True], [potential], [boost])
        boost, potential = float(new[0]), potential + points[0]
        assert boost <= rules.academy_boost_cap
    assert (boost, potential) == (8.0, 88.0)


def test_a_cap_lowered_later_never_takes_a_boost_back(world: World) -> None:
    rules = _rules(world, academy_boost_cap=5.0)
    new, points = _step(rules, [19.0], [2500], [True], [88.0], [8.0])
    assert new.tolist() == [8.0] and points == [0]


def test_the_boost_never_lifts_potential_past_the_ceiling(world: World) -> None:
    rules = _rules(world)
    potential, boost = 92.0, 0.0  # two points of room
    for _ in range(40):
        new, points = _step(rules, [19.0], [2500], [True], [potential], [boost])
        boost, potential = float(new[0]), potential + points[0]
    assert (potential, boost) == (94.0, 2.0)  # stopped at the ceiling, nothing banked
    # Already at the ceiling, or above it (an unusual potential): nothing, and nothing taken.
    new, points = _step(rules, [19.0] * 2, [2500] * 2, [True] * 2, [94.0, 96.0], [1.5, 0.0])
    assert new.tolist() == [1.5, 0.0] and points == [0, 0]
    # A fraction already carried isn't lost on the way to the ceiling: 3.6 -> 4.0, one point.
    potential, boost, total = 93.0, 3.6, 0
    for _ in range(6):
        new, points = _step(rules, [19.0], [2500], [True], [potential], [boost])
        boost, potential, total = float(new[0]), potential + points[0], total + points[0]
    assert (total, potential, boost) == (1, 94.0, 4.0)


def test_a_player_who_stops_qualifying_keeps_what_he_has(world: World) -> None:
    rules = _rules(world)
    new, points = _step(rules, [19.0, 23.0], [500, 2500], [True, True], [85.0, 85.0],
                        [2.5, 2.5])
    assert new.tolist() == [2.5, 2.5] and points == [0, 0]  # benched, or too old now


def test_the_boost_is_the_same_every_time(world: World) -> None:
    """It uses no randomness, so any order or repetition gives the same potential."""
    rules = _rules(world)
    ages = [19.0, 20.5, 17.2, 22.5, 21.0]
    minutes = [2400, 1800, 3000, 2600, 900]
    academy = [True, True, True, True, True]
    potential = [78.0, 91.0, 66.0, 80.0, 70.0]
    boost = [0.5, 1.75, 7.9, 3.0, 0.0]
    first = _step(rules, ages, minutes, academy, potential, boost)
    again = _step(rules, ages, minutes, academy, potential, boost)
    assert first[0].tolist() == again[0].tolist() and first[1] == again[1]
