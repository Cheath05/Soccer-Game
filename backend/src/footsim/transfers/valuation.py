"""Players' market values (W4-1; docs/calibration/value-model.md).

A log-linear model fitted on the base world's Transfermarkt values (``footsim fit-values``):
overall (at a different rate above a knee), age (youth adds, decline after the late twenties,
faster past the early thirties), a premium for young stars, keepers cheaper, and his club's
reputation as the market he's priced in.
It's computed on demand, for anyone, so a value moves as a player develops, ages or changes
club. Contract time left isn't part of the value: it's part of the asking price (W4-4).
"""

from datetime import date

import numpy as np
from numpy.typing import ArrayLike, NDArray

from footsim.defs.valuation import ValuationDef

FEATURES = ("intercept", "overall", "above_knee", "decline", "late_decline", "young",
            "young_star", "goalkeeper", "reputation")


def years_old(birth_date: str, day: date) -> float:
    """Age in years to the day (not whole years), so a value doesn't jump on a birthday."""
    return (day - date.fromisoformat(birth_date)).days / 365.25


def features(model: ValuationDef, overall: ArrayLike, age: ArrayLike, goalkeeper: ArrayLike,
             reputation: ArrayLike) -> NDArray[np.float64]:
    """The model's terms for each player (rows), in ``FEATURES`` order."""
    ovr = np.asarray(overall, dtype=float)
    years = np.asarray(age, dtype=float)
    rep = np.asarray(reputation, dtype=float)
    return np.column_stack([
        np.ones_like(ovr),
        ovr - model.reference_overall,
        np.maximum(0.0, ovr - model.knee),
        np.maximum(0.0, years - model.decline_from),
        np.maximum(0.0, years - model.late_from),
        np.maximum(0.0, model.young_until - years),
        np.maximum(0.0, ovr - model.star_from) * np.maximum(0.0, model.star_until - years),
        np.asarray(goalkeeper, dtype=float),
        rep - model.reference_reputation,
    ])


def coefficients(model: ValuationDef) -> NDArray[np.float64]:
    return np.array([model.intercept, model.overall, model.above_knee, -model.decline,
                     -model.late_decline, model.young, model.young_star, model.goalkeeper,
                     model.reputation])


def _rounded(value: NDArray[np.float64]) -> NDArray[np.int64]:
    """To the steps a market quotes: €25K below €1M, €100K below €10M, €500K below €50M,
    €1M above."""
    step = np.select([value < 1e6, value < 1e7, value < 5e7], [25_000, 100_000, 500_000],
                     1_000_000)
    rounded: NDArray[np.int64] = (np.round(value / step) * step).astype(np.int64)
    return rounded


def quote_eur(value: float) -> int:
    """One amount in euros, quoted in market steps (as values are)."""
    return int(_rounded(np.array([float(value)]))[0])


def plain_values(model: ValuationDef, overall: ArrayLike, age: ArrayLike,
                 goalkeeper: ArrayLike, reputation: ArrayLike) -> NDArray[np.float64]:
    """The model's values in euros, unrounded and without a player's own premium."""
    result: NDArray[np.float64] = np.exp(
        features(model, overall, age, goalkeeper, reputation) @ coefficients(model))
    return result


def values_eur(model: ValuationDef, overall: ArrayLike, age: ArrayLike, goalkeeper: ArrayLike,
               reputation: ArrayLike, premium: ArrayLike = 0.0) -> NDArray[np.int64]:
    """Market values in euros, vectorised and quoted. ``reputation`` is the owning club's (a
    free agent's own); ``premium`` his stored market premium (log)."""
    raw = plain_values(model, overall, age, goalkeeper, reputation) * np.exp(
        np.asarray(premium, dtype=float))
    return np.maximum(_rounded(raw), model.minimum_eur)


def value_eur(model: ValuationDef, overall: float, age: float, goalkeeper: bool,
              reputation: float, premium: float = 0.0) -> int:
    """One player's market value in euros."""
    return int(values_eur(model, [overall], [age], [float(goalkeeper)], [reputation],
                          [premium])[0])

