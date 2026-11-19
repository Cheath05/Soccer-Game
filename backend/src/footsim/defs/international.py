"""International football (W8, docs/plans/w8-w10-international.md): every FIFA member's national
team (data/config/international/teams.yaml), the names for made-up home-based players (names.yaml)
and the rules for squads and those players (rules.yaml)."""

from pydantic import Field, model_validator

from footsim.defs.common import DefModel

CONFEDERATIONS = ("UEFA", "CONMEBOL", "CONCACAF", "AFC", "CAF", "OFC")


class TeamDef(DefModel):
    code: str  # FIFA's code: ESP, CIV...
    name: str
    confederation: str
    elo: int = Field(gt=0)  # World Football Elo, when the data was taken
    names: list[str] = []  # the game's spellings of the nationality, when they differ from name

    @model_validator(mode="after")
    def _confederation(self) -> "TeamDef":
        if self.confederation not in CONFEDERATIONS:
            raise ValueError(f"{self.code}: unknown confederation {self.confederation}")
        return self

    @property
    def nationalities(self) -> list[str]:
        """Every spelling of the nationality, the team's name first."""
        return [self.name, *(n for n in self.names if n != self.name)]


class TeamsFile(DefModel):
    teams: list[TeamDef]


class NameRegionDef(DefModel):
    donors: list[str] = []  # nations whose people's names the region borrows
    nations: list[str]
    first: list[str] = []
    last: list[str] = []


class NamesDef(DefModel):
    own_names_min: int = Field(ge=1)
    regions: dict[str, NameRegionDef]


class LevelDef(DefModel):
    at_1900: float
    per_elo_point: float = Field(gt=0)
    min: float
    max: float

    def of(self, elo: float) -> float:
        """A nation's level (its best XI's average overall) from its Elo."""
        return min(self.max, max(self.min, self.at_1900 + self.per_elo_point * (elo - 1900)))


class ReputationDef(DefModel):
    at_1500: float
    per_elo_point: float

    def of(self, elo: float) -> int:
        return int(round(min(99.0, max(1.0, self.at_1500 + self.per_elo_point * (elo - 1500)))))


class WindowsDef(DefModel):
    first_after_days: int = Field(ge=0)
    spacing_days: int = Field(ge=1)
    max_matchdays: int = Field(ge=1)


class FriendliesDef(DefModel):
    elo_noise: float = Field(ge=0)
    cross_confederation: float = Field(ge=0, le=1)


class EloDef(DefModel):
    home_advantage: float = Field(ge=0)
    k: dict[str, float]  # by match: friendly, qualifier, finals


class InternationalRulesDef(DefModel):
    level: LevelDef
    reputation: ReputationDef
    places: dict[str, tuple[int, int]]  # by position: [starters, reserves]
    depth_drop: float = Field(ge=0)
    margin: float = Field(ge=0)
    quality_sd: float = Field(ge=0)
    ages: tuple[int, int]
    potential_room: int = Field(ge=0)
    windows: WindowsDef
    friendlies: FriendliesDef
    elo: EloDef

    @property
    def squad_size(self) -> int:
        """A squad's players: every place, starters and reserves."""
        return sum(a + b for a, b in self.places.values())


class InternationalDef(DefModel):
    teams: dict[str, TeamDef]  # by FIFA code
    names: NamesDef
    rules: InternationalRulesDef

    @model_validator(mode="after")
    def _regions(self) -> "InternationalDef":
        for key, region in self.names.regions.items():
            unknown = sorted(set(region.donors + region.nations) - set(self.teams))
            if unknown:
                raise ValueError(f"names region {key}: unknown teams {unknown}")
        return self
