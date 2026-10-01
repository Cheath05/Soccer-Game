"""Player development (people/development.py): players grow towards their ceiling through their
twenties, reach it around their peak age, hold it, and decline from their early thirties; a rare
few keep their prime longer. Each month a few attributes move on their own, and built-up
progress moves every attribute together a point at a time."""

import numpy as np
import pytest

from footsim.defs.development import DevelopmentDef
from footsim.defs.positions import PositionGroup
from footsim.domain.attributes import ATTR_INDEX, AttrGroup, attributes_in
from footsim.match.synthetic import synthetic_player
from footsim.people.development import DevelopmentInput, Traits, apply_month, draw_traits
from footsim.world.context import World, get_world


@pytest.fixture(scope="module")
def world() -> World:
    return get_world()


def _quiet(world: World) -> DevelopmentDef:
    return world.defs.development.model_copy(update={"noise": 0.0})


def _traits(peak: float = 27.5, decline: float = 32.0, bonus: float = 0.0,
            ageless: bool = False) -> Traits:
    return Traits(peak_age=np.array([peak]), decline_age=np.array([decline]),
                  ceiling_bonus=np.array([bonus]), ageless=np.array([ageless]))


def _career(world: World, rules: DevelopmentDef, traits: Traits, start_age: float,
            end_age: float, quality: float, potential: float,
            minutes: float = 2500.0) -> list[tuple[float, float]]:
    """(age, overall) every month from ``start_age`` to ``end_age``."""
    attrs = synthetic_player(world.defs, 1, "CM", quality, np.random.default_rng(3)).attrs
    a, progress = attrs[None, :].astype(float), np.zeros(1)
    rng = np.random.default_rng(0)
    history, age = [], start_age
    while age < end_age:
        inp = DevelopmentInput(attrs=a, ages=np.array([age]), potential=np.array([potential]),
                               groups=[PositionGroup.CM], minutes=np.array([minutes]))
        a, progress, _ = apply_month(rules, world.model, inp, traits, progress, rng)
        age += 1 / 12
        history.append((age, float(world.model.group_overalls(a)[PositionGroup.CM][0])))
    return history


def _at(history: list[tuple[float, float]], age: float) -> float:
    return next(overall for a, overall in history if a >= age)


def test_a_young_regular_reaches_his_ceiling_in_his_prime_and_holds_it(world: World) -> None:
    history = _career(world, _quiet(world), _traits(bonus=2.0), 18.0, 31.5, 60.0, 80.0)
    ceiling = 80.0 + 2.0
    assert _at(history, 18.5) < 66
    assert _at(history, 27.5) >= ceiling - 2.0  # there by his peak age
    assert _at(history, 27.5) <= ceiling + 1.0
    assert abs(_at(history, 31.4) - _at(history, 28.0)) <= 1.0  # and holds it


def test_decline_starts_in_his_early_thirties_unless_he_is_ageless(world: World) -> None:
    rules = _quiet(world)
    normal = _career(world, rules, _traits(decline=32.0), 30.0, 36.0, 80.0, 80.0)
    lost = _at(normal, 31.9) - _at(normal, 35.9)
    expected = -sum(rules.decline_by_year[:4])
    assert lost == pytest.approx(expected, abs=1.5)
    assert abs(_at(normal, 31.9) - _at(normal, 30.1)) <= 1.0  # nothing lost before it starts
    ageless = _career(world, rules, _traits(decline=32.0, ageless=True), 30.0, 36.0, 80.0, 80.0)
    assert _at(ageless, 31.9) - _at(ageless, 35.9) <= 1.0  # still in his prime at 36


def test_ageless_players_are_rare_and_mostly_the_best(world: World) -> None:
    rules = world.defs.development
    rng = np.random.default_rng(1)
    ordinary = draw_traits(rules, np.full(20000, 70.0), rng)
    elite = draw_traits(rules, np.full(20000, 90.0), rng)
    assert ordinary.ageless.mean() < 0.005
    assert 0.06 < elite.ageless.mean() < 0.14
    above = ordinary.ceiling_bonus > 0
    assert 0.25 < above.mean() < 0.35  # some go past their potential
    assert ordinary.peak_age.min() >= rules.peak_age[0]
    assert ordinary.decline_age.min() >= rules.decline_start[0]


def test_a_whole_point_of_progress_moves_every_attribute(world: World) -> None:
    rules = _quiet(world).model_copy(update={"specific_share": 0.0})
    attrs = synthetic_player(world.defs, 2, "CM", 65.0, np.random.default_rng(4)).attrs
    a = attrs[None, :].astype(float)
    inp = DevelopmentInput(attrs=a, ages=np.array([20.0]), potential=np.array([85.0]),
                           groups=[PositionGroup.CM], minutes=np.array([2500.0]))
    new, progress, moves = apply_month(rules, world.model, inp, _traits(), np.array([0.99]),
                                       np.random.default_rng(0))
    assert moves[0] == 1
    keeping = {ATTR_INDEX[g] for g in attributes_in(AttrGroup.GOALKEEPING)}
    outfield = [i for i in range(a.shape[1]) if i not in keeping]
    assert np.all(new[0, outfield] - a[0, outfield] == 1)  # every outfield attribute up a point
    assert 0.0 <= progress[0] < 0.99


def test_a_month_also_moves_a_few_individual_attributes(world: World) -> None:
    rules = _quiet(world).model_copy(update={"specific_share": 1.0})
    attrs = synthetic_player(world.defs, 3, "CM", 60.0, np.random.default_rng(5)).attrs
    a = np.repeat(attrs[None, :].astype(float), 50, axis=0)
    inp = DevelopmentInput(attrs=a, ages=np.full(50, 18.0), potential=np.full(50, 85.0),
                           groups=[PositionGroup.CM] * 50, minutes=np.full(50, 2500.0))
    traits = Traits(peak_age=np.full(50, 27.5), decline_age=np.full(50, 32.0),
                    ceiling_bonus=np.zeros(50), ageless=np.zeros(50, dtype=bool))
    new, _, moves = apply_month(rules, world.model, inp, traits, np.zeros(50),
                                np.random.default_rng(2))
    changed = (new != a).sum(axis=1)
    assert np.all(moves == 0)  # no whole-point moves: every change is individual
    assert 1 <= np.median(changed) <= 6  # a handful of attributes each, not every one
