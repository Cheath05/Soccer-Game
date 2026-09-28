"""Shared building blocks for game-definition data files (data/config)."""

import math
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from footsim.domain.attributes import ATTRIBUTES


class DefModel(BaseModel):
    """Base for all definition models: immutable, and unknown keys are errors (catches typos)."""

    model_config = ConfigDict(extra="forbid", frozen=True)


Unit = Annotated[float, Field(ge=0.0, le=1.0)]
SignedUnit = Annotated[float, Field(ge=-1.0, le=1.0)]


class Point(DefModel):
    """Normalised pitch point from the attacking team's view.

    x: 0 = own goal line, 1 = opponent goal line.
    y: 0 = left touchline, 1 = right touchline (facing the opponent goal).
    """

    x: Unit
    y: Unit


class Offset(DefModel):
    dx: SignedUnit = 0.0
    dy: SignedUnit = 0.0


def _check_attribute_keys(weights: dict[str, float]) -> dict[str, float]:
    unknown = sorted(set(weights) - set(ATTRIBUTES))
    if unknown:
        raise ValueError(f"unknown attributes: {unknown}")
    return weights


def _check_sums_to_one(weights: dict[str, float]) -> dict[str, float]:
    if any(w < 0 for w in weights.values()):
        raise ValueError("weights must be non-negative")
    total = sum(weights.values())
    if not math.isclose(total, 1.0, abs_tol=1e-6):
        raise ValueError(f"weights must sum to 1.0, got {total:.6f}")
    return weights


AttributeDeltas = Annotated[dict[str, float], AfterValidator(_check_attribute_keys)]
"""Signed per-attribute adjustments (e.g. a role's weight modifiers)."""

AttributeWeights = Annotated[
    dict[str, float],
    AfterValidator(_check_attribute_keys),
    AfterValidator(_check_sums_to_one),
]
"""Non-negative per-attribute weights that sum to 1."""
