"""Player development rules (data/config/rules/development.yaml): see people/development.py."""

from pydantic import Field, model_validator

from footsim.defs.common import DefModel


class DevelopmentDef(DefModel):
    growth_by_age: list[tuple[int, float]]  # (up to age, share of the gap closed in a year)
    late_growth: float = Field(ge=0, le=1)  # the share once past his peak age
    minutes: list[tuple[int, float]]  # (minutes in the past year up to, growth factor)
    heavy_minutes: float = Field(gt=0)  # factor beyond the last minutes band
    bench_credit_minutes: float = Field(ge=0)  # minutes credited per match as an unused sub
    bench_decay: float = Field(ge=0, le=1)  # share of the bench credit kept from month to month
    academy_max_age: int = Field(ge=0)  # the academy boost lasts to this age (whole years)
    academy_regular_minutes: float = Field(ge=0)  # real minutes in a year that make a regular
    academy_boost_per_year: float = Field(ge=0)  # potential points a year while he is one
    academy_boost_cap: float = Field(ge=0)  # the most the boost ever adds to a potential
    academy_potential_ceiling: int = Field(ge=1, le=99)  # potential the boost never lifts past
    peak_age: tuple[float, float]  # a player's own peak age is drawn from this range
    beyond_potential: list[tuple[float, int, int]]  # (chance, low, high) extra on his ceiling
    decline_start: tuple[float, float]  # the age his decline starts, drawn from this range
    decline_by_year: list[float]  # overall points a year, from the first year of decline on
    ageless_chance: list[tuple[int, float]]  # (from potential, chance) of keeping his prime
    ageless_delay: float = Field(ge=0)  # years his decline starts later
    ageless_slowdown: float = Field(ge=0, le=1)  # share of the normal decline once it starts
    noise: float = Field(ge=0)  # a year's random swing in overall (sd)
    specific_share: float = Field(ge=0, le=1)  # of each month's change, on individual attributes
    news_min_change: float = Field(ge=0)  # the least change in overall the news reports
    trend_memory: float = Field(ge=0, lt=1)  # share of last month's trend his trend keeps
    trend_shown: float = Field(ge=0)  # trend (overall a month) that shows an up or down arrow

    @model_validator(mode="after")
    def _ordered(self) -> "DevelopmentDef":
        for low, high in (self.peak_age, self.decline_start):
            if low > high:
                raise ValueError("ranges must be (low, high)")
        if sum(c for c, _, _ in self.beyond_potential) > 1:
            raise ValueError("beyond_potential chances add up to more than 1")
        return self
