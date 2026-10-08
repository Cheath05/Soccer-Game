"""The transfer market's rules (W4): data/config/transfers/market.yaml."""

from typing import Self

from pydantic import Field, model_validator

from footsim.defs.common import DefModel


class RoleMultipliers(DefModel):
    key: float = Field(gt=0)
    starter: float = Field(gt=0)
    rotation: float = Field(gt=0)
    surplus: float = Field(gt=0)


class AnswerWeights(DefModel):
    """The player's answer to a move: weights of what he weighs up."""

    reputation: float = Field(ge=0)
    wage: float = Field(ge=0)
    starting: float = Field(ge=0)
    listed: float = Field(ge=0)
    noise: float = Field(ge=0)


class MarketDef(DefModel):
    default_window_nation: str  # whose windows a club from a country without a calendar follows
    interval_days: int = Field(ge=1)
    deadline_days: int = Field(ge=0)
    deadline_activity: float = Field(ge=0, le=1)
    outside_league_activity: float = Field(ge=0, le=1)
    max_in_summer: int = Field(ge=0)
    max_in_winter: int = Field(ge=0)
    max_out: int = Field(ge=0)
    needs_per_day: int = Field(ge=1)
    offer_days: int = Field(ge=1)
    max_bids_for_user: int = Field(ge=0)
    bids_per_window: int = Field(ge=0)
    moved_rest_days: int = Field(ge=0)
    max_news: int = Field(ge=0)
    candidates_per_need: int = Field(ge=1)
    loan_max_age: float = Field(gt=0)
    loan_level_gap: float = Field(ge=0)
    loan_share: float = Field(ge=0, le=1)
    depth_per_slot: int = Field(ge=1)
    keepers_wanted: int = Field(ge=1)
    squad_max: int = Field(ge=11)
    weak_gap: float = Field(ge=0)
    improve_urgency: float = Field(ge=0, le=1)
    min_improvement: float = Field(ge=0)
    upgrade_band: tuple[float, float]
    depth_band: tuple[float, float]
    ageing_from: float
    key_margin: float = Field(ge=0)
    reach: float = Field(ge=0)
    role_multiplier: RoleMultipliers
    contract_multiplier: list[tuple[float, float]]  # (years left under, multiplier)
    listed_multiplier: float = Field(gt=0)
    distressed_multiplier: float = Field(gt=0)
    counter_from: float = Field(gt=0, le=1)
    bid_eagerness: tuple[float, float]
    max_premium: float = Field(gt=0)
    urgent_premium: float = Field(ge=0)
    max_deal_share: float = Field(gt=0, le=1)
    move_raise: float = Field(ge=1)
    free_agent_discount: float = Field(gt=0, le=1)
    max_wage_share: float = Field(gt=0, le=1)
    wage_slack: float = Field(ge=0)
    contract_years: list[tuple[float, int]]  # (age up to, years)
    answer: AnswerWeights

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        for name in ("upgrade_band", "depth_band", "bid_eagerness"):
            low, high = getattr(self, name)
            if high < low:
                raise ValueError(f"{name}: {low} > {high}")
        for name in ("contract_multiplier", "contract_years"):
            limits = [row[0] for row in getattr(self, name)]
            if limits != sorted(limits):
                raise ValueError(f"{name} must rise")
        return self
