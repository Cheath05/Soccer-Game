"""How clubs' reputations move between seasons: data/config/rules/reputation.yaml."""

from pydantic import Field

from footsim.defs.common import DefModel


class ReputationDriftDef(DefModel):
    drift: float = Field(ge=0, le=1)
    league_weight: float = Field(ge=0, le=1)
    title_bonus: float = Field(ge=0)
    cup_bonus: float = Field(ge=0)
    news_change: float = Field(ge=0)
