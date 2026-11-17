"""US college soccer (W9a, the NCAA Division I men's season): the programs and conferences
(data/config/college/ncaa_d1.yaml) and the rules of the season, its rosters, recruiting and the
draft pool (data/config/college/rules.yaml)."""

import re
from datetime import date

from pydantic import Field, field_validator, model_validator

from footsim.defs.common import DefModel
from footsim.defs.competitions import PointsRule, Tiebreaker

CLASS_NAMES = {1: "Fr", 2: "So", 3: "Jr", 4: "Sr"}
_MONTH_DAY = re.compile(r"^\d\d-\d\d$")


def on(month_day: str, season_start: date) -> date:
    """A season's date from "MM-DD": in the autumn of the season starting ``season_start`` (July
    to December), or the spring after it (January to June)."""
    month, day = (int(x) for x in month_day.split("-"))
    return date(season_start.year + (1 if month < season_start.month else 0), month, day)


def _month_day(value: str) -> str:
    if not _MONTH_DAY.match(value):
        raise ValueError(f"{value!r} is not MM-DD")
    month, day = (int(x) for x in value.split("-"))
    date(2027, month, day)  # a real day
    return value


class ProgramDef(DefModel):
    school: str
    nickname: str
    state: str
    tier: int = Field(ge=1, le=5)

    @property
    def name(self) -> str:
        """The club's name in the world: "Indiana Hoosiers"."""
        return f"{self.school} {self.nickname}"


class ConferenceDef(DefModel):
    name: str
    short_name: str
    tournament: int = Field(ge=0)  # teams in its tournament; 0: the table's champion gets the bid
    auto_bid: bool = True
    teams: list[ProgramDef]

    @model_validator(mode="after")
    def _sizes(self) -> "ConferenceDef":
        if self.tournament > len(self.teams):
            raise ValueError(f"{self.name}: a tournament of {self.tournament} with "
                             f"{len(self.teams)} teams")
        if self.tournament == 1:
            raise ValueError(f"{self.name}: a tournament needs two teams or none")
        return self


class ProgramsFile(DefModel):
    conferences: dict[str, ConferenceDef]

    @model_validator(mode="after")
    def _unique(self) -> "ProgramsFile":
        names = [t.name for c in self.conferences.values() for t in c.teams]
        repeated = sorted({n for n in names if names.count(n) > 1})
        if repeated:
            raise ValueError(f"programs listed twice: {repeated}")
        bad = [k for k in self.conferences if not k.isalnum()]
        if bad:
            raise ValueError(f"conference keys must be letters and digits: {bad}")
        return self


class RegularSeasonDef(DefModel):
    start: str  # MM-DD
    end: str
    matches: int = Field(ge=1)  # each team's regular-season matches, as near as pairing allows
    slots: int = Field(ge=1)  # match days: a few more than matches, for non-conference pairing

    @field_validator("start", "end")
    @classmethod
    def _dates(cls, value: str) -> str:
        return _month_day(value)

    @model_validator(mode="after")
    def _room(self) -> "RegularSeasonDef":
        if self.slots < self.matches:
            raise ValueError("fewer match days than matches")
        return self


class TournamentDef(DefModel):
    rounds: list[str]  # a date (MM-DD) per round, the last the final's
    extra_time: bool = True
    penalties: bool = True

    @field_validator("rounds")
    @classmethod
    def _dates(cls, value: list[str]) -> list[str]:
        return [_month_day(x) for x in value]


class NcaaTournamentDef(TournamentDef):
    teams: int = Field(ge=2)
    seeds: int = Field(ge=0)  # the seeded teams, who have byes into the second round
    selection: str  # MM-DD: the field is picked and seeded
    neutral_from: int = Field(ge=0)  # the round from which games are at a neutral ground
    round_names: list[str]

    @model_validator(mode="after")
    def _names(self) -> "NcaaTournamentDef":
        if len(self.round_names) != len(self.rounds):
            raise ValueError("a name for each round of the NCAA tournament")
        return self

    @field_validator("selection")
    @classmethod
    def _selection(cls, value: str) -> str:
        return _month_day(value)


class RankingDef(DefModel):
    """The RPI: weights of a team's winning share, its opponents' and their opponents'."""

    weights: tuple[float, float, float]
    draw_value: float = Field(ge=0, le=1)  # a draw (or a shoot-out) as part of a win


class RosterDef(DefModel):
    size: tuple[int, int]  # a program's roster, from and to
    shape: list[str]  # positions by depth, cycled for a bigger roster
    class_shares: dict[int, float]  # Fr, So, Jr, Sr
    age: dict[int, float]  # a class's mean age on 1 July
    age_sd: float = Field(ge=0)
    age_range: tuple[float, float]
    level_by_tier: dict[int, float]  # a program's mean overall (a sophomore's) by tier
    level_sd: float = Field(ge=0)  # programs of a tier differ by this much
    class_offset: dict[int, float]  # a class above or below the program's level
    player_sd: float = Field(ge=0)  # players about their class's level
    player_sd_cap: float = Field(gt=0)  # ...at most this many spreads away
    template_pool: int = Field(ge=1)  # attributes copied from one of this many nearest pros
    reputation_by_tier: dict[int, int]  # the program's reputation (fixed: it doesn't drift)
    foreign_share: float = Field(ge=0, le=1)  # international players on a roster
    foreign_nations: list[str]  # where they come from (nation names)


class PotentialDef(DefModel):
    room_by_class: dict[int, float]  # mean potential above his overall by class
    room_sd: float = Field(ge=0)
    min_room: float = Field(ge=0)
    star_share: float = Field(ge=0, le=1)  # the rare player with far more to come...
    star_bonus: tuple[float, float]  # ...this much more
    max_potential: int = Field(ge=1, le=99)


class RecruitingDef(DefModel):
    """Each program's freshman class at a season's start, to fill its roster again."""

    roster_target: int = Field(ge=11)
    recruits: tuple[int, int]  # a class's size, at least and at most
    age: float  # a recruit's mean age on 1 July
    age_sd: float = Field(ge=0)


class DraftDef(DefModel):
    """Who leaves college after the College Cup, and what becomes of the undrafted."""

    underclassmen: int = Field(ge=0)  # Generation adidas: the best underclassmen who declare
    min_potential: int  # an underclassman declares only with this much potential
    release: str  # MM-DD (the spring): prospects nobody drafted become free agents
    grace_seasons: int = Field(ge=0)  # an undrafted free agent unsigned this long retires

    @field_validator("release")
    @classmethod
    def _release(cls, value: str) -> str:
        return _month_day(value)


class CollegeRulesDef(DefModel):
    key: str  # the competition's key
    name: str
    short_name: str
    nation: str  # nation code
    source_league: str  # the clubs' source league
    formation: str  # every program plays it
    points: PointsRule = PointsRule()
    tiebreakers: list[Tiebreaker]
    regular_season: RegularSeasonDef
    conference_tournament: TournamentDef
    ncaa: NcaaTournamentDef
    ranking: RankingDef
    roster: RosterDef
    potential: PotentialDef
    recruiting: RecruitingDef
    draft: DraftDef


class CollegeDef(DefModel):
    rules: CollegeRulesDef
    conferences: dict[str, ConferenceDef]

    @model_validator(mode="after")
    def _field(self) -> "CollegeDef":
        bids = sum(c.auto_bid for c in self.conferences.values())
        teams = sum(len(c.teams) for c in self.conferences.values())
        ncaa = self.rules.ncaa
        if bids > ncaa.teams or ncaa.teams > teams:
            raise ValueError(f"an NCAA field of {ncaa.teams} with {bids} automatic bids and "
                             f"{teams} teams")
        if ncaa.seeds > ncaa.teams:
            raise ValueError("more seeds than teams")
        rounds = (ncaa.teams - 1).bit_length()
        if len(ncaa.rounds) != rounds:
            raise ValueError(f"the NCAA tournament of {ncaa.teams} has {rounds} rounds, "
                             f"{len(ncaa.rounds)} dates")
        largest = max((c.tournament for c in self.conferences.values()), default=0)
        if largest and (largest - 1).bit_length() > len(self.rules.conference_tournament.rounds):
            raise ValueError(f"a conference tournament of {largest} needs more round dates")
        return self

    def program_conference(self) -> dict[str, str]:
        """Each program's club name -> its conference's key."""
        return {t.name: key for key, c in self.conferences.items() for t in c.teams}
