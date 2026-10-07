"""API response and request models."""

from datetime import date

from pydantic import BaseModel, Field


class ClubRef(BaseModel):
    id: int
    name: str


class ClubOption(ClubRef):
    reputation: int
    average_overall: float


class LeagueOption(BaseModel):
    key: str
    name: str
    tier: int
    clubs: list[ClubOption]
    nation: str = ""  # the league's country code (ENG, ESP...)


class SaveSlotOut(BaseModel):
    slot: int
    has_save: bool
    has_autosave: bool
    saved_at: str | None
    club: str | None
    manager: str | None
    game_date: str | None
    active: bool


class NewCareerIn(BaseModel):
    club_id: int
    manager_name: str
    # The sandbox: the club's transfer budget to start with, up to EUR 10bn (the owner puts in
    # the cash to back it). None: the board's own budget.
    transfer_budget_eur: int | None = Field(default=None, ge=0, le=10_000_000_000)


class FixtureOut(BaseModel):
    id: int
    date: str
    competition: str
    competition_name: str
    stage: str
    round: int
    tie: str | None
    leg: int | None
    home: ClubRef
    away: ClubRef
    neutral: bool
    status: str
    home_goals: int | None
    away_goals: int | None
    extra_time: bool
    home_pens: int | None
    away_pens: int | None
    stage_name: str | None = None  # a cup round's name ("Third round"); None otherwise


class CupTieOut(BaseModel):
    tie: str
    home: ClubRef  # drawn first
    away: ClubRef | None  # None: a bye, the home club is exempt
    fixtures: list[FixtureOut]  # one, or two for a two-legged tie
    winner: ClubRef | None


class CupRoundOut(BaseModel):
    index: int
    name: str
    dates: list[str]
    legs: int
    drawn: bool  # False: not drawn yet
    ties: list[CupTieOut]


class CupOut(BaseModel):
    key: str
    name: str
    nation: str
    season: str
    rounds: list[CupRoundOut]
    winner: ClubRef | None


class CupSummaryOut(BaseModel):
    key: str
    name: str
    nation: str  # the country it is played in (a nation code: ENG)
    current_round: str | None  # the round being played or next to be played
    user_status: str | None  # the user's club: "In the third round", "Out", "Winners"...
    winner: ClubRef | None


class CupRunOut(BaseModel):
    """How far a club went in a cup in one season."""

    key: str
    name: str
    reached: str  # the last round it played in, or "Winners"
    won: bool
    out: bool  # knocked out (False while still in it)


class TableRowOut(BaseModel):
    position: int
    club: ClubRef
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
    zone: str | None
    form: list[str]
    outcome: str | None = None  # a finished season's: champion | promoted | playoff_winner |
    #                             playoffs | relegated


class TableOut(BaseModel):
    competition: str
    name: str
    season: str
    final: bool = False  # the season is over and this is its final table
    started: bool = True  # at least one match has been played
    first_match: str | None = None  # the date of its first league match
    rows: list[TableRowOut]


class SeasonOut(BaseModel):
    id: int
    label: str
    current: bool
    finished: bool = True  # its league tables are final (the current season's are, from May)


class ClubSeasonOut(BaseModel):
    """A club's league season: its final position, or its position so far this season."""

    season_id: int
    season: str
    competition: "CompetitionOut"
    position: int | None  # None before the season's first match
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    points: int
    outcome: str | None  # champion | promoted | playoff_winner | playoffs | relegated
    final: bool  # False for the season in progress
    managed: bool  # the user managed the club that season
    cups: list[CupRunOut] = []


class ClubHistoryOut(BaseModel):
    club: ClubRef
    seasons: list[ClubSeasonOut]  # newest first
    titles: int  # league titles won in the career so far
    promotions: int
    relegations: int


class CompetitionOut(BaseModel):
    key: str
    name: str
    tier: int
    nation: str = ""  # the league's country code (ENG, ESP...); empty for a cup


class CareerOut(BaseModel):
    slot: int
    date: str
    season: str
    season_end: str  # the last day of the season's calendar (play-offs may run past it)
    manager: str | None
    club: ClubRef
    competition: CompetitionOut | None
    position: int | None
    next_fixture: FixtureOut | None
    recent: list[FixtureOut]


class AdvanceOut(BaseModel):
    date: str
    stop: str
    fixture_id: int | None
    messages: list[str]
    season_final: "SeasonFinalOut | None" = None  # when it stopped at the season's end


class SimIn(BaseModel):
    until: date  # simulate up to (not including) this day


class SimResultOut(BaseModel):
    fixture_id: int
    date: str
    home: str
    away: str
    home_goals: int
    away_goals: int
    outcome: str  # W | D | L for the user's club


class SeasonFinalOut(BaseModel):
    """How the user's club finished a league season (league_final)."""

    competition: str
    position: int
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    points: int
    outcome: str | None  # champion | promoted | playoff_winner | relegated | playoffs | None
    cups: list["CupRunOut"] = []  # how far the club went in each cup
    review: "SeasonReviewOut | None" = None  # how it went everywhere else, and for the squad
    news: list[str] = []  # the other news from the sim: what the review doesn't cover


class SimStatusOut(BaseModel):
    running: bool
    start: str
    until: str
    date: str  # how far it has got
    results: list[SimResultOut]  # the user's matches played, in order
    messages: list[str]  # news on the way
    stop: str | None  # date | season_end | cancelled | abandoned | error
    error: str | None
    season_final: SeasonFinalOut | None = None  # when it stopped at the season's end


class SquadPlayerOut(BaseModel):
    id: int
    name: str
    short_name: str
    position: str
    positions: list[str]
    age: int
    nationality: str | None
    overall: int
    trend: int  # his overall lately: 1 rising, -1 falling, 0 steady
    season_start_overall: int | None = None  # his overall as this season began; None if unknown
    condition: int
    form: float
    injury: str | None
    injured_until: str | None
    suspended: int
    value_eur: int
    wage_weekly_eur: int
    contract_end: str
    height_cm: int | None
    preferred_foot: str
    appearances: int
    goals: int
    assists: int
    average_rating: float | None


class ClubPlayerOut(BaseModel):
    """A player as seen from outside his club: ability and availability, without the fitness
    and wage detail only his own club knows. The transfer fields stay empty until the
    transfer market exists."""

    id: int
    name: str
    position: str
    positions: list[str]
    age: int
    nationality: str | None
    overall: int
    trend: int  # his overall lately: 1 rising, -1 falling, 0 steady
    status: str  # available | injured | suspended
    value_eur: int
    contract_end: str
    form: float
    appearances: int
    goals: int
    transfer_status: str | None = None
    interested_clubs: list[ClubRef] = []


class ClubOverviewOut(BaseModel):
    club: ClubRef
    own_club: bool
    nation: str | None
    competition: CompetitionOut | None
    position: int | None  # None before the season starts
    points: int | None
    played: int
    reputation: int
    stadium_name: str | None
    stadium_capacity: int | None
    manager: str | None  # None until computer managers exist
    wage_bill_weekly_eur: int
    transfer_budget_eur: int  # rounded for clubs other than the user's
    balance_eur: int  # likewise
    squad_size: int
    average_age: float
    average_overall: float
    top_players: list[ClubPlayerOut]
    recent: list[FixtureOut]  # latest first
    upcoming: list[FixtureOut]
    recent_transfers: list[str]  # always empty until the transfer market exists


class AttributeOut(BaseModel):
    key: str
    value: int


class RoleRatingOut(BaseModel):
    key: str
    name: str
    position_group: str
    rating: int


class PotentialOut(BaseModel):
    low: int
    high: int
    label: str


class HonourOut(BaseModel):
    """A competition's winners at a season's end: a league's champions or a cup's. (A play-off's
    winners are not champions: they show as promoted clubs.)"""

    kind: str  # league | cup
    key: str
    name: str
    nation: str  # the country it belongs to (a nation code: ENG)
    tier: int  # a league's; 0 for a cup
    winner: ClubRef


class HeadlineOut(BaseModel):
    """A notable result of the season, built from the database: the champions of a major
    league, a cup won by a far weaker club. Continental titles will be another kind."""

    kind: str  # league_title | cup_upset (| continental_title, once those competitions exist)
    text: str
    club: ClubRef
    competition: str
    nation: str  # a nation code, or "" for a competition that has none
    detail: str | None = None


class ClubMoveOut(BaseModel):
    """A club going up or down a league at the season's end."""

    club: ClubRef
    nation: str
    from_league: str
    to_league: str
    position: int | None  # where it finished in the league it left
    via_playoffs: bool = False


class DevelopmentOut(BaseModel):
    """One of the user's players whose overall changed over the season."""

    player_id: int
    name: str
    position: str
    age: int
    before: int  # his overall as the season began
    after: int  # and as it ended
    change: int


class RetirementOut(BaseModel):
    player_id: int
    name: str
    position: str
    age: int
    overall: int
    club: ClubRef | None
    own_player: bool


class YouthIntakeOut(BaseModel):
    """A youngster who joined the user's academy."""

    player_id: int
    name: str
    position: str
    age: int
    overall: int
    potential: PotentialOut  # as the club's coaches see it


class SeasonReviewOut(BaseModel):
    """The season that has just ended, across the game and for the user's squad."""

    season: str
    next_season: str | None
    honours: list[HonourOut]
    headlines: list[HeadlineOut] = []  # notable results: shown first in the other news
    promoted: list[ClubMoveOut]
    relegated: list[ClubMoveOut]
    development: list[DevelopmentOut]  # best improvement first
    development_recorded: bool  # False: the season began before the game kept the record
    development_since: str | None  # the day it began being kept, when that was after the start
    retired: list[RetirementOut]  # the user's players and the notable ones
    youth: list[YouthIntakeOut]  # the user's academy intake


class PlayerSeasonLineOut(BaseModel):
    """A player's season in one competition (or, on a total row, in all of them)."""

    club: ClubRef | None  # None on a total row
    competition_key: str
    competition: str
    appearances: int  # starts and substitute appearances
    starts: int
    minutes: int
    goals: int
    assists: int
    average_rating: float | None
    yellow: int
    red: int


class PlayerSeasonOut(BaseModel):
    season_id: int
    season: str
    lines: list[PlayerSeasonLineOut]  # one per competition
    total: PlayerSeasonLineOut


class PlayerDetailOut(SquadPlayerOut):
    # Only a player's own club knows his fitness and wage: None for everyone else's.
    condition: int | None  # type: ignore[assignment]
    wage_weekly_eur: int | None  # type: ignore[assignment]
    club: ClubRef | None
    weight_kg: int | None
    weak_foot: int
    skill_moves: int
    attributes: dict[str, list[AttributeOut]]
    face: dict[str, int]
    face_key: list[str]  # the headline ratings that count most towards his overall
    roles: list[RoleRatingOut]
    familiarity: dict[str, int]
    potential: PotentialOut
    traits: list[str]
    own_player: bool
    retired: bool = False


class MatchEventOut(BaseModel):
    minute: int
    label: str  # how the time is written: 23' or 45+2'
    period: int | None
    second: int | None
    type: str
    club_id: int
    player: str | None
    other_player: str | None
    detail: str | None


class PlayerLineOut(BaseModel):
    player_id: int
    name: str
    started: bool
    minutes: int
    goals: int
    assists: int
    shots: int
    shots_on_target: int
    passes: int
    passes_completed: int
    tackles: int
    interceptions: int
    saves: int
    yellow: int
    red: int
    rating: float


class MatchOut(BaseModel):
    fixture: FixtureOut
    events: list[MatchEventOut]
    home_lines: list[PlayerLineOut]
    away_lines: list[PlayerLineOut]
    stats: dict[str, dict[str, float]] | None


class SlotOut(BaseModel):
    id: str
    position: str
    x: float
    y: float
    default_role: str


class FormationOut(BaseModel):
    key: str
    name: str
    slots: list[SlotOut]


class RoleOut(BaseModel):
    key: str
    name: str
    group: str
    description: str


class InstructionOut(BaseModel):
    key: str
    label: str
    options: list[str]
    default: str


class SheetEntryOut(BaseModel):
    slot: str | None
    position: str
    role: str
    player_id: int
    name: str
    number: int
    rating: int
    condition: int


class TacticsOut(BaseModel):
    formation: str
    roles: dict[str, str]
    lineup: dict[str, int] | None
    instructions: dict[str, str]
    starters: list[SheetEntryOut]
    bench: list[SheetEntryOut]
    formations: list[FormationOut]
    roles_by_group: dict[str, list[RoleOut]]
    instruction_options: list[InstructionOut]


class TacticsIn(BaseModel):
    formation: str
    roles: dict[str, str]
    lineup: dict[str, int] | None
    instructions: dict[str, str]


class FinanceLineOut(BaseModel):
    """Money of one kind this season (the user's club)."""

    kind: str
    label: str
    amount_eur: int


class LedgerRowOut(BaseModel):
    date: str
    kind: str
    label: str
    amount_eur: int


class BoardOut(BaseModel):
    """The board's view (display only): where it expects the club to finish, where it is, and
    how confident it is (0-100)."""

    target: int | None
    position: int | None
    played: int
    league_size: int | None
    confidence: int | None
    mood: str


class FinancesOut(BaseModel):
    """The user's club's money (W3). Amounts in euros; the page converts for display."""

    club: ClubRef
    season: str
    league: str | None
    balance_eur: int
    transfer_budget_eur: int
    wage_budget_weekly_eur: int
    wage_bill_weekly_eur: int
    projected_revenue_eur: int  # this season's, as the club plans it
    income: list[FinanceLineOut]  # this season so far
    expenses: list[FinanceLineOut]
    net_eur: int
    recent: list[LedgerRowOut]
    board: BoardOut
