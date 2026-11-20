"""International football (W8, docs/plans/w8-w10-international.md): every FIFA member's national
team (data/config/international/teams.yaml), the names for made-up home-based players (names.yaml)
and the rules for squads and those players (rules.yaml)."""

from typing import Any

from pydantic import Field, ValidationError, model_validator

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
    """Places in an earlier stage that enter a stage (qualifiers.yaml)."""

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


    @property
    def places(self) -> int:
        """How many teams it sends to the finals."""
        if self.format == "groups" and self.qualified_ranks is not None:
            return (self.qualified_ranks[1] - self.qualified_ranks[0] + 1) * self.groups
        return self.paths if self.format == "paths" and self.qualified_winners else 0


def _shift_window(window: str, years: int) -> str:
    year, month = window.split("-")
    return f"{int(year) + years}-{month}"


class QualifiersDef(DefModel):
    """The qualifiers' template (qualifiers.yaml): the stages as the ``cycle`` edition plays
    them."""

    cycle: int  # the edition the stages' windows are written for
    draw_days_before: int = Field(ge=1)
    stages: list[QualifierStageDef]

    def for_edition(self, year: int, changes: dict[str, dict[str, Any]]
                    ) -> list[QualifierStageDef]:
        """The stages of the ``year`` edition: every window moved on by the years since
        ``cycle``, then the edition's ``changes`` (a changed field's value as given)."""
        unknown = sorted(set(changes) - {s.key for s in self.stages})
        if unknown:
            raise ValueError(f"World Cup {year}: changes to unknown stages {unknown}")
        stages = []
        for stage in self.stages:
            raw = stage.model_dump(by_alias=True)
            raw["windows"] = [_shift_window(w, year - self.cycle) for w in stage.windows]
            raw.update(changes.get(stage.key, {}))
            try:
                stages.append(QualifierStageDef.model_validate(raw))
            except ValidationError as exc:
                raise ValueError(f"World Cup {year}, {stage.key}: {exc}") from exc
        keys = [s.key for s in stages]
        for k, stage in enumerate(stages):
            for source in stage.entrants.from_:
                if source.stage not in keys[:k]:
                    raise ValueError(f"World Cup {year}, {stage.key}: enters from "
                                     f"{source.stage}, not an earlier stage")
        return stages


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


class WorldCupEditionDef(DefModel):
    """One World Cup's hosts, and the changes to the qualifiers' stages their places need."""

    hosts: list[str]
    stages: dict[str, dict[str, Any]] = {}  # by stage key: fields to change


class WorldCupDef(DefModel):
    """The World Cup finals (W8 I4, world_cup.yaml): ISO dates of the draw and each round (the
    first edition's: a later one's fall on the same days of its year), and the editions."""
    year: int  # the first edition
    every_years: int = Field(default=4, ge=1)
    editions: dict[int, WorldCupEditionDef]
    draw: str
    groups: list[str] = Field(min_length=3, max_length=3)
    round_of_32: str
    round_of_16: str
    quarter_finals: str
    semi_finals: str
    third_place: str
    final: str

    @model_validator(mode="after")
    def _editions(self) -> "WorldCupDef":
        expected = [self.year + k * self.every_years for k in range(len(self.editions))]
        if sorted(self.editions) != expected:
            raise ValueError(f"the World Cup's editions must be {expected}, one every "
                             f"{self.every_years} years from {self.year}")
        return self

    def is_edition(self, year: int) -> bool:
        return year >= self.year and (year - self.year) % self.every_years == 0

    def edition(self, year: int) -> WorldCupEditionDef:
        """An edition's hosts and changes: its own, or (after the listed ones) the listed
        editions' in turn."""
        if year in self.editions:
            return self.editions[year]
        k = (year - self.year) // self.every_years
        return self.editions[sorted(self.editions)[k % len(self.editions)]]


SLOTS = 48  # the finals' teams


class InternationalDef(DefModel):
    teams: dict[str, TeamDef]  # by FIFA code
    names: NamesDef
    rules: InternationalRulesDef
    qualifiers: QualifiersDef  # every World Cup's, from a template (W8 I3)
    club_world_cup: ClubWorldCupDef  # W10
    world_cup: WorldCupDef  # the finals and the editions (W8 I4)

    @model_validator(mode="after")
    def _regions(self) -> "InternationalDef":
        for key, region in self.names.regions.items():
            unknown = sorted(set(region.donors + region.nations) - set(self.teams))
            if unknown:
                raise ValueError(f"names region {key}: unknown teams {unknown}")
        guests = sorted({g.country for g in self.club_world_cup.guests} - set(self.teams))
        if guests:
            raise ValueError(f"guest clubs of unknown countries {guests}")
        for year, edition in self.world_cup.editions.items():
            unknown = sorted(set(edition.hosts) - set(self.teams))
            if unknown:
                raise ValueError(f"World Cup {year}: unknown hosts {unknown}")
            stages = self.qualifiers.for_edition(year, edition.stages)
            places = len(edition.hosts) + sum(s.places for s in stages)
            if places != SLOTS:
                raise ValueError(f"World Cup {year}: the hosts and the qualifiers' places make "
                                 f"{places}, not {SLOTS}")
        return self
