"""API response and request models."""

from datetime import date

from pydantic import BaseModel


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


class TableOut(BaseModel):
    competition: str
    name: str
    season: str
    rows: list[TableRowOut]


class CompetitionOut(BaseModel):
    key: str
    name: str
    tier: int


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
    budget_estimate_eur: int  # a rough guess from the wage bill and reputation
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
