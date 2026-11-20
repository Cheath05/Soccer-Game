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


class EntrantSourceDef(DefModel):
    """Places in an earlier stage that enter a stage (qualifiers_2030.yaml)."""

    stage: str
    ranks: tuple[int, int] | None = None  # those ranks in every group
    best: int | None = None  # the best ``best`` teams at ``rank`` across the groups
    rank: int | None = None
    winners: bool = False  # its paths' winners
    losers: bool = False  # its paths' finals' losers


class EntrantsDef(DefModel):
    confederation: str | None = None  # its best ``top`` teams by Elo, hosts aside
    top: int | None = None
    from_: list[EntrantSourceDef] = Field(default=[], alias="from")


class QualifierStageDef(DefModel):
    key: str
    name: str
    confederation: str
    format: str  # groups | paths
    groups: int = 1
    paths: int = 1
    legs: int = Field(default=2, ge=1, le=2)
    neutral: bool = False
    windows: list[str]  # "YYYY-MM": the windows its matches are played in, in order
    entrants: EntrantsDef
    qualified_ranks: tuple[int, int] | None = None  # groups: these ranks qualify
    qualified_winners: bool = False  # paths: the winners qualify

    @model_validator(mode="after")
    def _format(self) -> "QualifierStageDef":
        if self.format not in ("groups", "paths"):
            raise ValueError(f"{self.key}: unknown format {self.format}")
        return self


class QualifiersDef(DefModel):
    cycle: int  # the World Cup's year
    hosts: list[str]
    draw_days_before: int = Field(ge=1)
    stages: list[QualifierStageDef]


class GuestClubDef(DefModel):
    name: str
    country: str  # FIFA code
    confederation: str
    level: float  # its best XI's average overall
    stadium: str | None = None
    capacity: int | None = None


class CwcSlotsDef(DefModel):
    slots: int = Field(ge=0)
    per_country: int = Field(ge=1)


class CwcDatesDef(DefModel):
    groups: list[str]  # "MM-DD" of each group matchday
    round_of_16: str
    quarter_finals: str
    semi_finals: str
    final: str


class CwcPrizesDef(DefModel):
    participation: dict[str, float]  # by confederation
    win: float
    draw: float
    round_of_16: float
    quarter_finals: float
    semi_finals: float
    final: float
    champions: float


class ClubWorldCupDef(DefModel):
    first_year: int
    every_years: int = Field(ge=1)
    host: str  # FIFA code
    draw: str  # "MM-DD", the year before
    title_bonus: float = Field(ge=0)
    dates: CwcDatesDef
    prizes: CwcPrizesDef
    slots: dict[str, CwcSlotsDef]
    guests: list[GuestClubDef]

    @model_validator(mode="after")
    def _shape(self) -> "ClubWorldCupDef":
        if sum(s.slots for s in self.slots.values()) != 31:
            raise ValueError("the Club World Cup's confederation slots must make 31 (and a host)")
        return self


class InternationalDef(DefModel):
    teams: dict[str, TeamDef]  # by FIFA code
    names: NamesDef
    rules: InternationalRulesDef
    qualifiers: QualifiersDef  # the next World Cup's (W8 I3)
    club_world_cup: ClubWorldCupDef  # W10

    @model_validator(mode="after")
    def _regions(self) -> "InternationalDef":
        for key, region in self.names.regions.items():
            unknown = sorted(set(region.donors + region.nations) - set(self.teams))
            if unknown:
                raise ValueError(f"names region {key}: unknown teams {unknown}")
        stages = [s.key for s in self.qualifiers.stages]
        for k, stage in enumerate(self.qualifiers.stages):
            for source in stage.entrants.from_:
                if source.stage not in stages[:k]:
                    raise ValueError(f"{stage.key}: enters from {source.stage}, not an earlier "
                                     "stage")
        guests = sorted({g.country for g in self.club_world_cup.guests} - set(self.teams))
        if guests:
            raise ValueError(f"guest clubs of unknown countries {guests}")
        unknown = sorted(set(self.qualifiers.hosts) - set(self.teams))
        if unknown:
            raise ValueError(f"unknown hosts {unknown}")
        return self
