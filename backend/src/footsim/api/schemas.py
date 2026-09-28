"""API response and request models."""

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


class SquadPlayerOut(BaseModel):
    id: int
    name: str
    short_name: str
    position: str
    positions: list[str]
    age: int
    nationality: str | None
    overall: int
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
    club: ClubRef | None
    weight_kg: int | None
    weak_foot: int
    skill_moves: int
    attributes: dict[str, list[AttributeOut]]
    face: dict[str, int]
    roles: list[RoleRatingOut]
    familiarity: dict[str, int]
    potential: PotentialOut
    traits: list[str]
    own_player: bool


class MatchEventOut(BaseModel):
    minute: int
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
    passes: int
    passes_completed: int
    tackles: int
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
