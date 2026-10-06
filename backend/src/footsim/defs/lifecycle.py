"""Careers ending and starting (data/config/rules/lifecycle.yaml): see world/lifecycle.py."""

from pydantic import Field, model_validator

from footsim.defs.common import DefModel


class RetirementDef(DefModel):
    by_age: list[tuple[int, float]]  # (from age, chance he retires at a season's end)
    keeper_years: int = Field(ge=0)  # keepers play this many years longer
    ageless_factor: float = Field(ge=0)  # an ageless player's chance is scaled by this
    good_from: float  # a player at least this good keeps going longer...
    good_factor: float = Field(ge=0)
    poor_below: float  # ...and one below this stops sooner
    poor_factor: float = Field(ge=0)
    free_agent_factor: float = Field(ge=0)  # nobody has signed him
    free_agent_leave: float = Field(ge=0, le=1)  # an unsigned free agent leaves the game
    news_from: float  # other clubs' players this good make the news when they retire

    @model_validator(mode="after")
    def _ascending(self) -> "RetirementDef":
        ages = [a for a, _ in self.by_age]
        if ages != sorted(ages):
            raise ValueError("by_age must run from the youngest age up")
        return self


class YouthDef(DefModel):
    intake: list[tuple[int, int]]  # (club reputation from, players a year)
    ages: tuple[int, int]
    overall: list[tuple[int, float]]  # (club reputation from, mean overall of a new player)
    overall_sd: float = Field(ge=0)
    potential: list[tuple[int, float]]  # (club reputation from, mean potential)
    potential_sd: float = Field(ge=0)
    potential_room: float = Field(ge=0)  # potential at least this far above his overall
    max_potential: int = Field(ge=1, le=99)
    home_nation: float = Field(ge=0, le=1)  # share from the club's own country
    positions: dict[str, float]  # position code -> share of intakes
    contract_age: int  # his first contract runs to the end of the season he turns this


class SquadsDef(DefModel):
    max_players: int = Field(ge=11)  # a computer-run club with more releases its weakest...
    keep: int = Field(ge=11)  # ...down to this many

    @model_validator(mode="after")
    def _ordered(self) -> "SquadsDef":
        if self.keep > self.max_players:
            raise ValueError("keep must not exceed max_players")
        return self


class LifecycleDef(DefModel):
    retirement: RetirementDef
    youth: YouthDef
    squads: SquadsDef
