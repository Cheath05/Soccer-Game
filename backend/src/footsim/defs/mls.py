"""MLS's roster rules (data/config/rules/mls.yaml): see world/mls.py.

Every amount here is US dollars a year, as MLS publishes them; world/mls.py converts them to the
game's euros at finance.yaml's dollar rate."""

from typing import Self

from pydantic import Field, model_validator

from footsim.defs.common import DefModel


class RosterModelDef(DefModel):
    designated_players: int = Field(ge=0)
    u22_players: int = Field(ge=0)
    extra_gam: float = Field(ge=0)  # a season's GAM on top of the annual (expires with it)


class TamDef(DefModel):
    by_season: dict[int, float]  # by the calendar year the season starts in
    ceiling: float = Field(gt=0)
    floor: float = Field(ge=0)

    def for_year(self, year: int) -> float:
        """The allotment of the season starting in ``year`` (the latest one known after)."""
        known = sorted(self.by_season)
        chosen = known[0]
        for y in known:
            if y <= year:
                chosen = y
        return self.by_season[chosen]


class GamDef(DefModel):
    annual: float = Field(ge=0)
    max_share: float = Field(ge=0, le=1)
    floor: float = Field(ge=0)
    from_sales_cap: float = Field(ge=0)
    missed_playoffs: float = Field(ge=0)


class MlsAiDef(DefModel):
    gam_reserve_share: float = Field(ge=0, le=1)
    spare_slots_kept: int = Field(ge=0)


class SuperDraftDef(DefModel):
    """MLS's SuperDraft (W9a B5): college prospects (world/college) picked in January."""

    date: str  # "MM-DD" in the January of the season
    rounds: int = Field(ge=1)
    reminder_days: int = Field(ge=0)  # the user's club hears of it this long before
    # A pick's value to a club: his overall plus this share of the potential above it (as the
    # club's scouts see it: potential with a club's own error of this spread), plus a bonus for a
    # position group the club is short in.
    potential_weight: float = Field(ge=0)
    scouting_sd: float = Field(ge=0)
    need_bonus: float = Field(ge=0)
    # The players a club wants in each position group, for the need.
    group_targets: dict[str, int]
    # Signing: a pick from the first round is paid the senior minimum, a later one the reserve
    # minimum (the senior minimum if he's older than the reserve age); contracts of these years,
    # Generation adidas picks' longer. AI clubs sign the picks of the first ``ai_sign_rounds``
    # rounds when the rules allow; the rest keep their rights only.
    contract_years: int = Field(ge=1)
    ga_contract_years: int = Field(ge=1)
    ga_seasons: int = Field(ge=1)  # Generation adidas (the supplemental roster) this many seasons
    ai_sign_rounds: int = Field(ge=0)
    rights_seasons: int = Field(ge=1)  # an unsigned pick's rights last this many seasons

    def month_day(self) -> tuple[int, int]:
        month, day = (int(x) for x in self.date.split("-"))
        return month, day


class MlsStartDef(DefModel):
    model1_min_third_overall: float
    dp_reference_overall: float
    dp_reference_wage: float = Field(gt=0)
    dp_per_point: float = Field(gt=1)
    dp_min_wage: float = Field(gt=0)
    budget_headroom: float = Field(ge=0)
    homegrown_max_age: int = Field(ge=0)

    def dp_wage(self, overall: float) -> float:
        return max(self.dp_min_wage, self.dp_reference_wage * float(
            self.dp_per_point ** (overall - self.dp_reference_overall)))


class MlsRulesDef(DefModel):
    league: str
    source_league: str
    domestic_nations: dict[str, list[str]]
    canadian_clubs: list[str]
    canadian_minimum: int = Field(ge=0)
    salary_budget: float = Field(gt=0)
    max_charge: float = Field(gt=0)
    senior_minimum: float = Field(gt=0)
    reserve_minimum: float = Field(gt=0)
    empty_slot_below: int = Field(ge=0)
    senior_slots: int = Field(ge=1)
    supplemental_slots: int = Field(ge=0)
    supplemental_senior_slots: int = Field(ge=0)
    reserve_max_age: int
    homegrown_supplemental_max: float = Field(gt=0)
    roster_models: dict[int, RosterModelDef]
    dp_charges: list[tuple[int, float]]
    dp_charge: float = Field(gt=0)
    dp_secondary_window_share: float = Field(gt=0, le=1)
    third_dp_fee: float = Field(ge=0)
    young_dp_max_age: int
    u22_signing_max_age: int
    u22_max_age: int
    u22_charges: list[tuple[int, float]]
    u22_charge: float = Field(gt=0)
    u22_max_wage: float = Field(gt=0)
    tam: TamDef
    gam: GamDef
    sale_share: float = Field(ge=0, le=1)
    trade_min_cash: float = Field(ge=0)
    international_slots: int = Field(ge=0)
    slot_price_gam: float = Field(ge=0)
    green_card_seasons: int = Field(ge=1)
    ai: MlsAiDef
    start: MlsStartDef
    superdraft: SuperDraftDef

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.supplemental_senior_slots > self.supplemental_slots:
            raise ValueError("supplemental_senior_slots can't exceed supplemental_slots")
        if self.reserve_minimum > self.senior_minimum:
            raise ValueError("the reserve minimum can't exceed the senior minimum")
        if self.tam.ceiling <= self.max_charge:
            raise ValueError("TAM's ceiling must be above the maximum charge")
        for table in (self.dp_charges, self.u22_charges):
            if [a for a, _ in table] != sorted(a for a, _ in table):
                raise ValueError("age tables run from the youngest age up")
        if not self.roster_models:
            raise ValueError("at least one roster model")
        return self

    @staticmethod
    def by_age(table: list[tuple[int, float]], default: float, age: int) -> float:
        """The first entry whose age bound ``age`` is within, else ``default``."""
        for bound, amount in table:
            if age <= bound:
                return amount
        return default
