"""The market-value model (W4-1): its shape, as fitted (data/config/transfers/valuation.yaml)."""

from datetime import date

import numpy as np
import pytest

from footsim.calibration.value_fit import fit_base_world
from footsim.core.paths import data_dir
from footsim.defs.valuation import ValuationDef
from footsim.transfers.valuation import FEATURES, coefficients, features, value_eur, values_eur
from footsim.world.context import get_world

BASE_WORLD = data_dir() / "worlds" / "base-2026-27.sqlite"


def _model() -> ValuationDef:
    return get_world().defs.valuation


def test_better_players_are_worth_more_at_every_age() -> None:
    model = _model()
    for age in (18, 23, 27, 31, 35):
        values = values_eur(model, np.arange(50, 95), np.full(45, age), np.zeros(45),
                            np.full(45, 70))
        assert (np.diff(values) >= 0).all(), age
        assert values[-1] > values[0] * 100, age


def test_value_peaks_young_and_falls_with_age() -> None:
    model = _model()
    by_age = values_eur(model, np.full(20, 75), np.arange(17, 37), np.zeros(20), np.full(20, 70))
    assert (np.diff(by_age) <= 0).all()  # an equal player is worth less every year older
    young_star = value_eur(model, 86, 19, False, 85)
    prime_star = value_eur(model, 86, 27, False, 85)
    assert young_star > 1.5 * prime_star


def test_keepers_are_cheaper_and_big_clubs_dearer() -> None:
    model = _model()
    assert value_eur(model, 80, 26, True, 70) < value_eur(model, 80, 26, False, 70)
    assert value_eur(model, 80, 26, False, 85) > value_eur(model, 80, 26, False, 55)


def test_values_are_quoted_in_market_steps_above_a_floor() -> None:
    model = _model()
    values = values_eur(model, np.arange(40, 95), np.full(55, 25), np.zeros(55), np.full(55, 70))
    for v in values:
        step = 25_000 if v < 1e6 else 100_000 if v < 1e7 else 500_000 if v < 5e7 else 1_000_000
        assert v % step == 0 or v == model.minimum_eur, v
    assert value_eur(model, 30, 38, True, 0) == model.minimum_eur
    assert 1_000_000 < value_eur(model, 70, 25, False, 70) < 10_000_000


@pytest.mark.skipif(not BASE_WORLD.exists(), reason="base world not built")
def test_the_config_is_the_fit_of_the_base_world() -> None:
    """valuation.yaml holds `footsim fit-values` of the base world. This fails when the overall
    formula, positions or ratings change what the fit sees: refit (`footsim fit-values
    --write`) in the commit that changes them."""
    world = get_world()
    fit = fit_base_world(BASE_WORLD, world, world.defs.valuation, date(2026, 7, 1))
    assert fit.players > 10_000 and fit.r2 > 0.7
    for name in FEATURES:
        assert getattr(fit.model, name) == pytest.approx(getattr(world.defs.valuation, name),
                                                         abs=1e-4), name
    # The runtime model (signs and all) reproduces the fit's R² on the same players.
    overall, age, keeper, reputation, target = fit.sample
    predicted = features(world.defs.valuation, overall, age, keeper, reputation) @ coefficients(
        world.defs.valuation)
    r2 = 1 - ((target - predicted) ** 2).sum() / ((target - target.mean()) ** 2).sum()
    assert r2 == pytest.approx(fit.r2, abs=1e-3)
