"""Wages by league (data/config/finance/wage_levels.yaml) and club finances
(data/config/finance/finance.yaml)."""

from typing import Self

from pydantic import Field, model_validator

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


class LeagueIncome(DefModel):
    """A league's payments to each club for a season (EUR): an equal share, and merit."""

    base: float = Field(ge=0)
    merit: float = Field(ge=0)  # the champion's extra; falls linearly to nothing for last place

    def for_position(self, position: int, size: int) -> float:
        share = (size - position) / (size - 1) if size > 1 else 1.0
        return self.base + self.merit * share

    @property
    def expected(self) -> float:
        """What a mid-table club gets: the base and half the merit."""
        return self.base + self.merit / 2


class BoardRules(DefModel):
    confidence_start: int = Field(ge=0, le=100)
    per_place: float = Field(ge=0)
    max_step: float = Field(ge=0)
    min_played: int = Field(ge=0)  # league matches before the board judges the position


class FinanceDef(DefModel):
    """How clubs' money works (world/finance.py)."""

    league_income: dict[str, LeagueIncome]
    wage_ratio_start: float = Field(gt=0, le=1)
    club_income_floor: float = Field(ge=0)
    wage_budget_ratio: float = Field(gt=0, le=1.5)
    operating_costs: float = Field(ge=0, lt=1)
    starting_cash: float = Field(ge=0)
    budget_share: float = Field(ge=0)
    cash_share: float = Field(ge=0, le=1)
    reinvest: float = Field(ge=0, le=1)
    parachute: float = Field(ge=0, le=1)
    board: BoardRules

    @model_validator(mode="after")
    def _solvent(self) -> Self:
        """A club starts able to pay its wages and running costs, and its wage budget leaves
        room for the wages it already pays."""
        if self.wage_ratio_start + self.operating_costs >= 1:
            raise ValueError("wage_ratio_start + operating_costs must be below 1")
        if self.wage_budget_ratio < self.wage_ratio_start:
            raise ValueError("wage_budget_ratio must be at least wage_ratio_start")
        if self.wage_budget_ratio + self.operating_costs > 1:
            raise ValueError("wage_budget_ratio + operating_costs must be at most 1")
        return self
