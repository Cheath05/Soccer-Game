"""The market-value model (W4-1): data/config/transfers/valuation.yaml."""

from pydantic import Field

from footsim.defs.common import DefModel


class ValuationDef(DefModel):
    """log(value in EUR) = intercept + the terms below. The shape (where the knee and the age
    turns are) is set by hand; the coefficients are fitted by ``footsim fit-values`` on the base
    world's Transfermarkt values."""

    intercept: float
    reference_overall: float = 70.0
    overall: float  # per point of overall above the reference
    knee: float  # overall above which value grows at a different rate
    above_knee: float  # extra per point above the knee
    decline_from: float  # age from which value falls
    decline: float  # per year past decline_from
    late_from: float  # age from which it falls faster
    late_decline: float  # extra per year past late_from
    young_until: float  # age below which youth adds value (the years ahead of him)
    young: float  # per year below young_until
    star_from: float  # overall and ...
    star_until: float  # ... age between which a young star's market premium builds
    young_star: float  # per (overall − star_from) × (star_until − age), both above zero
    goalkeeper: float
    reference_reputation: float = 70.0
    reputation: float  # per point of his club's reputation (the league's market level)
    minimum_eur: int = Field(gt=0)
    fit: dict[str, float] = {}  # the fit's record: players, R², residual sd (log)
