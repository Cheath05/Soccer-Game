"""Wage levels by league (data/config/finance/wage_levels.yaml)."""

from pydantic import Field

from footsim.defs.common import DefModel


class WageLevel(DefModel):
    """Weekly gross wage (EUR) of a player at ``reference_overall`` in this league. Each
    overall point above or below multiplies the wage by ``per_point``."""

    reference_overall: float
    reference_wage: float = Field(gt=0)
    per_point: float = Field(gt=1)
    spread_sd: float = Field(default=0.25, ge=0)  # lognormal spread between players

    def wage_for(self, overall: float) -> float:
        return self.reference_wage * float(self.per_point ** (overall - self.reference_overall))


class WageLevelsFile(DefModel):
    default: WageLevel
    minimum_weekly_wage: float = Field(gt=0)
    leagues: dict[str, WageLevel] = {}

    def for_league(self, league: str) -> WageLevel:
        return self.leagues.get(league, self.default)
