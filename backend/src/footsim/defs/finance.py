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


class DisplayRules(DefModel):
    """What the finances page lists (api/finances.py)."""

    change_share: float = Field(ge=0)  # a monthly figure is listed as changed once it has moved
    change_amount: float = Field(ge=0)  # by this share of what it was, and by this much (EUR)
    changes_shown: int = Field(ge=1)  # changes listed, the latest first
    transactions_shown: int = Field(ge=1)  # one-off transactions listed, the latest first


class Currency(DefModel):
    """A currency the user can see money in (world/money.py)."""

    symbol: str = Field(min_length=1)
    per_euro: float = Field(gt=0)


class FinanceDef(DefModel):
    """How clubs' money works (world/finance.py)."""

    league_income: dict[str, LeagueIncome]
    # Prize money a cup's tie winner earns (EUR), by cup key: one amount for each of the cup's
    # rounds in order, the last the final's. The loader checks every cup has one.
    cup_prizes: dict[str, list[float]]
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
    display: DisplayRules
    # Money is kept in euros; the user sees it, and is quoted prices, in one of these (fixed
    # rates, display only). frontend/src/lib/format.ts keeps the same table.
    currencies: dict[str, Currency]

    @model_validator(mode="after")
    def _euro_is_base(self) -> Self:
        euro = self.currencies.get("EUR")
        if euro is None or euro.per_euro != 1:
            raise ValueError("currencies: EUR must be listed at per_euro 1")
        return self

    @model_validator(mode="after")
    def _prizes_rise(self) -> Self:
        """A cup pays something in every round, and no round less than the one before it (the
        final the most)."""
        for key, amounts in self.cup_prizes.items():
            if not amounts or min(amounts) < 0:
                raise ValueError(f"cup_prizes {key}: needs a prize for each round, none negative")
            if any(later < earlier for earlier, later in zip(amounts, amounts[1:], strict=False)):
                raise ValueError(f"cup_prizes {key}: prize money must not fall from one round "
                                 "to the next")
        return self

    @model_validator(mode="after")
    def _solvent(self) -> Self:
        """A club starts able to pay its wages and running costs, and its wage capacity leaves
        room for the wages it already pays."""
        if self.wage_ratio_start + self.operating_costs >= 1:
            raise ValueError("wage_ratio_start + operating_costs must be below 1")
        if self.wage_budget_ratio < self.wage_ratio_start:
            raise ValueError("wage_budget_ratio must be at least wage_ratio_start")
        if self.wage_budget_ratio + self.operating_costs > 1:
            raise ValueError("wage_budget_ratio + operating_costs must be at most 1")
        return self
