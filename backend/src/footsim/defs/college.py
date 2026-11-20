"""US college soccer (W9a, the NCAA Division I men's season): the programs and conferences
(data/config/college/ncaa_d1.yaml), the rules of the season, its rosters, recruiting and the
draft pool (data/config/college/rules.yaml), and high-school recruiting (W9c,
data/config/college/recruiting.yaml)."""

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


class ContinueStopsDef(DefModel):
    """The days Continue stops a college coach on (world/college/season.py ``stop_days``)."""

    ncaa_selection: bool = True
    ncaa_final: bool = True
    superdraft: bool = True
    recruiting: bool = True
    monthly: bool = True


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
    continue_stops: ContinueStopsDef = Field(default_factory=ContinueStopsDef)


class AbilityDef(DefModel):
    """A recruit's overall when he enrolls and his room to grow."""

    overall: float
    overall_sd: float = Field(ge=0)
    overall_range: tuple[float, float]
    room: float
    room_sd: float = Field(ge=0)
    min_room: float = Field(ge=0)
    star_share: float = Field(ge=0, le=1)
    star_bonus: tuple[float, float]
    max_potential: int = Field(ge=1, le=99)


class GradeDef(DefModel):
    """The recruiting services' grade, rankings and stars."""

    potential_weight: float = Field(ge=0, le=1)
    error_sd: float = Field(ge=0)
    stars: dict[int, int]  # stars -> the last national rank with them (5, 4, 3; the rest 2)

    @model_validator(mode="after")
    def _order(self) -> "GradeDef":
        if sorted(self.stars) != [3, 4, 5]:
            raise ValueError("stars: give the last rank of 5, 4 and 3 stars")
        if not self.stars[5] < self.stars[4] < self.stars[3]:
            raise ValueError("stars: the ranks must grow from 5 stars to 3")
        return self


Curve = list[tuple[float, float]]  # (national rank, value), linear between the points


def _curve(points: Curve) -> Curve:
    if len(points) < 2 or any(b[0] <= a[0] for a, b in zip(points, points[1:], strict=False)):
        raise ValueError("a curve needs two or more points with growing ranks")
    return points


class ExpectationsDef(DefModel):
    prestige: Curve  # the program prestige a recruit of a rank expects
    share: Curve  # the scholarship he hopes for

    @field_validator("prestige", "share")
    @classmethod
    def _points(cls, value: Curve) -> Curve:
        return _curve(value)


DECISION_PARTS = ("money", "prestige", "playing_time", "home", "attention")


class DecisionDef(DefModel):
    weights: dict[str, float]
    priority_shape: float = Field(gt=0)
    local_share: float = Field(ge=0, le=1)
    local_home: float = Field(ge=1)
    fit_sd: float = Field(ge=0)
    prestige_scale: float = Field(gt=0)
    home_miles: float = Field(gt=0)
    returning_growth: float
    bench_decay: float = Field(gt=0, le=1)
    readiness: dict[int, float]  # by stars, a week's growth
    readiness_sd: float = Field(ge=0)
    late_pace: float = Field(ge=1)
    waiting: dict[str, float]  # base, weight
    margin: float = Field(ge=0)
    flip_margin: float = Field(ge=0)
    flip_chance: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _parts(self) -> "DecisionDef":
        if set(self.weights) != set(DECISION_PARTS):
            raise ValueError(f"decision weights: give exactly {', '.join(DECISION_PARTS)}")
        if set(self.waiting) != {"base", "weight"}:
            raise ValueError("decision waiting: give base and weight")
        if set(self.readiness) != {2, 3, 4, 5}:
            raise ValueError("decision readiness: give 2 to 5 stars")
        return self


class RecruitingCalendarDef(DefModel):
    start: str
    signing_day: str  # the first Wednesday on or after this day
    close: str

    @field_validator("start", "signing_day", "close")
    @classmethod
    def _dates(cls, value: str) -> str:
        return _month_day(value)


PRIORITIES = ("top", "high", "watch")


class ProgramRulesDef(DefModel):
    roster_max: int = Field(ge=11)
    roster_target: int = Field(ge=11)
    funding_by_tier: dict[int, float]
    prestige_by_tier: dict[int, float]
    prestige_sd: float = Field(ge=0)
    prestige_rate: float = Field(ge=0, le=1)
    results_weight: float = Field(ge=0, le=1)
    results_seasons: int = Field(ge=1)
    ncaa_win_points: float = Field(ge=0)
    title_points: float = Field(ge=0)
    ncaa_win_buzz: float = Field(default=0.0, ge=0)  # prestige at once for an NCAA win
    title_buzz: float = Field(default=0.0, ge=0)  # and for the national title
    effort_by_tier: dict[int, float]
    priority_weight: dict[str, float]
    effort_cap: float = Field(gt=0)
    interest_gain: float = Field(ge=0)
    offer_boost: float = Field(ge=0)
    interest_decay: float = Field(ge=0, le=1)
    scouting_gain: float = Field(ge=0)
    official_visits: int = Field(ge=0)
    visit_interest: float = Field(ge=0, le=100)
    visit_boost: float = Field(ge=0)
    offer_overcommit: float = Field(ge=1)
    ai_error_by_tier: dict[int, float]
    ai_reach: float = Field(ge=0)
    ai_floor: float = Field(ge=0)
    need_bonus: float = Field(ge=0)
    crowd_penalty: float = Field(ge=0)
    ai_top_targets: int = Field(ge=0)
    share_step: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def _tiers(self) -> "ProgramRulesDef":
        for name in ("funding_by_tier", "prestige_by_tier", "effort_by_tier",
                     "ai_error_by_tier"):
            if set(getattr(self, name)) != {1, 2, 3, 4, 5}:
                raise ValueError(f"{name}: give tiers 1 to 5")
        if set(self.priority_weight) != set(PRIORITIES):
            raise ValueError(f"priority_weight: give {', '.join(PRIORITIES)}")
        if self.roster_target > self.roster_max:
            raise ValueError("roster_target is above roster_max")
        return self


class GodPlayerDef(DefModel):
    """A college coach's GOD player (world/college/god_player.py)."""

    every_seasons: int = Field(default=4, ge=1)
    overall: float = Field(default=78.0, ge=1, le=99)
    potential_room: int = Field(default=2, ge=0)
    age: float = Field(default=18.3, ge=15, le=25)


class UserRecruitingDef(DefModel):
    """A college coach's view of recruits and the rules of their offers."""

    overall_error_sd: float = Field(ge=0)
    overall_width: float = Field(ge=0)
    potential_error_sd: float = Field(ge=0)
    potential_width: float = Field(ge=0)
    width_floor: float = Field(ge=0)
    leader_knowledge: float = Field(ge=0, le=1)
    leader_rank: int = Field(ge=0)
    decommit_penalty: float = Field(ge=0)
    min_roster: int = Field(ge=11)
    class_points: dict[int, float]
    fit_labels: list[tuple[float, str]] = []  # (threshold, label), best first
    god_player: GodPlayerDef = Field(default_factory=GodPlayerDef)


class StateDef(DefModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    weight: float = Field(ge=0)


class HsRecruitingDef(DefModel):
    """High-school recruiting (W9c, data/config/college/recruiting.yaml)."""

    class_size: int = Field(ge=1)
    international_share: float = Field(ge=0, le=1)
    age: float
    age_sd: float = Field(ge=0)
    positions: dict[str, float]
    ability: AbilityDef
    grade: GradeDef
    expectations: ExpectationsDef
    decision: DecisionDef
    calendar: RecruitingCalendarDef
    programs: ProgramRulesDef
    user: UserRecruitingDef
    states: dict[str, StateDef]


class ProgramCostsDef(DefModel):
    scholarship: float = Field(ge=0)
    staff: dict[int, float]
    travel: float = Field(ge=0)


class TicketsDef(DefModel):
    fill: Curve  # (prestige, fill)
    form_games: int = Field(ge=1)
    form_weight: float = Field(ge=0)
    opponent_weight: float = Field(ge=0)
    event: dict[str, float]  # college | conference | ncaa
    min_fill: float = Field(ge=0, le=1)
    price: dict[int, float]

    @field_validator("fill")
    @classmethod
    def _points(cls, value: Curve) -> Curve:
        return _curve(value)


class BoostersDef(DefModel):
    per_win: float = Field(ge=0)
    conference_title: float = Field(ge=0)
    per_ncaa_win: float = Field(ge=0)
    national_title: float = Field(ge=0)
    prestige_scale: Curve

    @field_validator("prestige_scale")
    @classmethod
    def _points(cls, value: Curve) -> Curve:
        return _curve(value)


FACILITIES = ("training", "stadium")


class FacilityDef(DefModel):
    cost: list[float]  # to build each level from the one below (level 1's is 0)
    upkeep: list[float]  # a season, by level
    growth: list[float] | None = None  # training: extra monthly growth, by level
    capacity: list[int] | None = None  # stadium: seats, by level

    @model_validator(mode="after")
    def _levels(self) -> "FacilityDef":
        for name in ("cost", "upkeep", "growth", "capacity"):
            value = getattr(self, name)
            if value is not None and len(value) != 5:
                raise ValueError(f"{name}: give 5 levels")
        return self


class FacilitiesDef(DefModel):
    build_cutoff: str
    training: FacilityDef
    stadium: FacilityDef
    start_level: dict[str, dict[int, int]]  # facility -> tier -> level

    @field_validator("build_cutoff")
    @classmethod
    def _date(cls, value: str) -> str:
        return _month_day(value)

    @model_validator(mode="after")
    def _kinds(self) -> "FacilitiesDef":
        if self.training.growth is None or self.stadium.capacity is None:
            raise ValueError("training needs growth, the stadium capacity")
        if set(self.start_level) != set(FACILITIES):
            raise ValueError(f"start_level: give {', '.join(FACILITIES)}")
        return self

    def of(self, kind: str) -> FacilityDef:
        return self.training if kind == "training" else self.stadium


class CrowdDef(DefModel):
    min_scale: float = Field(ge=0, le=1)
    full_crowd: float = Field(gt=0)
    size_power: float = Field(gt=0)
    fill_weight: float = Field(ge=0, le=1)


class ProgramAiDef(DefModel):
    class_budget_share: float = Field(ge=0)
    reserve_seasons: float = Field(ge=0)
    priority: list[str]


class ProgramBuilderDef(DefModel):
    """The NCAA program builder mode (W9d, data/config/college/program.yaml). Money in dollars."""

    allocation: Curve  # (prestige, dollars a season)
    starting_balance: dict[int, float]
    costs: ProgramCostsDef
    tickets: TicketsDef
    boosters: BoostersDef
    ncaa_payout: list[float]  # by NCAA tournament round played
    facilities: FacilitiesDef
    appeal_per_level: float = Field(ge=0)
    crowd: CrowdDef
    ai: ProgramAiDef

    @field_validator("allocation")
    @classmethod
    def _points(cls, value: Curve) -> Curve:
        return _curve(value)


class CollegeDef(DefModel):
    rules: CollegeRulesDef
    conferences: dict[str, ConferenceDef]
    recruiting: HsRecruitingDef
    program: ProgramBuilderDef

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
        states = self.recruiting.states
        missing = sorted({t.state for c in self.conferences.values() for t in c.teams
                          if t.state not in states})
        if missing:
            raise ValueError(f"recruiting.yaml states: no centre for {missing}")
        return self

    def program_conference(self) -> dict[str, str]:
        """Each program's club name -> its conference's key."""
        return {t.name: key for key, c in self.conferences.items() for t in c.teams}
