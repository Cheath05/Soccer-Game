// Mirrors backend/src/footsim/api/schemas.py.

export interface ClubRef {
  id: number
  name: string
}

export interface ClubOption extends ClubRef {
  reputation: number
  average_overall: number
}

export interface LeagueOption {
  key: string
  name: string
  tier: number
  nation?: string // a nation code such as ENG; a server that predates it omits it
  clubs: ClubOption[]
}

export interface SaveSlot {
  slot: number
  has_save: boolean
  has_autosave: boolean
  saved_at: string | null
  club: string | null
  manager: string | null
  game_date: string | null
  active: boolean
}

export interface Fixture {
  id: number
  date: string
  competition: string
  competition_name: string
  stage: string
  round: number
  tie: string | null
  leg: number | null
  home: ClubRef
  away: ClubRef
  neutral: boolean
  status: 'scheduled' | 'played'
  home_goals: number | null
  away_goals: number | null
  extra_time: boolean
  home_pens: number | null
  away_pens: number | null
  stage_name: string | null // a cup round's name
}

export interface Competition {
  key: string
  name: string
  tier: number
  nation?: string // a nation code such as ENG; a server that predates it omits it
}

export interface Career {
  slot: number
  date: string
  season: string
  season_end: string // the last day of the season's calendar (play-offs may run past it)
  manager: string | null
  club: ClubRef
  competition: Competition | null
  position: number | null
  next_fixture: Fixture | null
  recent: Fixture[]
}

// Sim to date (api/sim.py): the career moving on to a chosen day in the background.
export interface SimResult {
  fixture_id: number
  date: string
  home: string
  away: string
  home_goals: number
  away_goals: number
  outcome: 'W' | 'D' | 'L'
}

export interface SeasonFinal {
  competition: string
  position: number
  played: number
  won: number
  drawn: number
  lost: number
  goals_for: number
  goals_against: number
  points: number
  outcome: string | null
  cups?: CupRun[] // how far the club went in each cup
}

export interface SimStatus {
  running: boolean
  start: string
  until: string
  date: string // how far it has got
  results: SimResult[]
  messages: string[]
  stop: 'date' | 'season_end' | 'cancelled' | 'abandoned' | 'error' | null
  error: string | null
  season_final?: SeasonFinal | null // when it stopped at the season's end
}

export interface AdvanceResult {
  date: string
  stop: 'match' | 'season_end' | 'limit'
  fixture_id: number | null
  messages: string[]
}

export interface TableRow {
  position: number
  club: ClubRef
  played: number
  won: number
  drawn: number
  lost: number
  goals_for: number
  goals_against: number
  goal_difference: number
  points: number
  zone: 'champion' | 'promotion' | 'playoff' | 'relegation' | null
  form: string[]
  outcome: Outcome | null // a finished season's
}

export interface Table {
  competition: string
  name: string
  season: string
  final: boolean // the season is over and this is its final table
  rows: TableRow[]
}

export type Outcome = 'champion' | 'promoted' | 'playoff_winner' | 'playoffs' | 'relegated'

export interface Season {
  id: number
  label: string
  current: boolean
}

/** A club's league season: its final position, or its position so far this season. */
export interface ClubSeason {
  season_id: number
  season: string
  competition: Competition
  position: number | null
  played: number
  won: number
  drawn: number
  lost: number
  goals_for: number
  goals_against: number
  points: number
  outcome: Outcome | null
  final: boolean
  managed: boolean
  cups: CupRun[]
}

export interface ClubHistory {
  club: ClubRef
  seasons: ClubSeason[] // newest first
  titles: number
  promotions: number
  relegations: number
}

export interface SquadPlayer {
  id: number
  name: string
  short_name: string
  position: string
  positions: string[]
  age: number
  nationality: string | null
  overall: number
  trend: number // his overall lately: 1 rising, -1 falling, 0 steady
  condition: number
  form: number
  injury: string | null
  injured_until: string | null
  suspended: number
  value_eur: number
  wage_weekly_eur: number
  contract_end: string
  height_cm: number | null
  preferred_foot: string
  appearances: number
  goals: number
  assists: number
  average_rating: number | null
}

/** Another club's player, seen from outside: no fitness or wage detail. */
export interface ClubPlayer {
  id: number
  name: string
  position: string
  positions: string[]
  age: number
  nationality: string | null
  overall: number
  trend: number // his overall lately: 1 rising, -1 falling, 0 steady
  status: 'available' | 'injured' | 'suspended'
  value_eur: number
  contract_end: string
  form: number
  appearances: number
  goals: number
  transfer_status: string | null // for the transfer market (not yet in the game)
  interested_clubs: ClubRef[]
}

export interface ClubOverview {
  club: ClubRef
  own_club: boolean
  nation: string | null
  competition: Competition | null
  position: number | null
  points: number | null
  played: number
  reputation: number
  stadium_name: string | null
  stadium_capacity: number | null
  manager: string | null
  wage_bill_weekly_eur: number
  budget_estimate_eur: number
  squad_size: number
  average_age: number
  average_overall: number
  top_players: ClubPlayer[]
  recent: Fixture[]
  upcoming: Fixture[]
  recent_transfers: string[]
}

export interface PlayerDetail extends Omit<SquadPlayer, 'condition' | 'wage_weekly_eur'> {
  condition: number | null // only for the user's own players
  wage_weekly_eur: number | null // only for the user's own players
  club: ClubRef | null
  weight_kg: number | null
  weak_foot: number
  skill_moves: number
  attributes: Record<string, { key: string; value: number }[]>
  face: Record<string, number>
  face_key: string[] // the headline ratings that count most towards his overall
  roles: { key: string; name: string; position_group: string; rating: number }[]
  familiarity: Record<string, number>
  potential: { low: number; high: number; label: string }
  traits: string[]
  own_player: boolean
  retired?: boolean
}

export interface MatchEvent {
  minute: number
  label: string
  period: number | null
  second: number | null
  type: string
  club_id: number
  player: string | null
  other_player: string | null
  detail: string | null
}

export interface PlayerLine {
  player_id: number
  name: string
  started: boolean
  minutes: number
  goals: number
  assists: number
  shots: number
  shots_on_target: number
  passes: number
  passes_completed: number
  tackles: number
  interceptions: number
  saves: number
  yellow: number
  red: number
  rating: number
}

export type TeamStats = Record<string, number>

export interface MatchReport {
  fixture: Fixture
  events: MatchEvent[]
  home_lines: PlayerLine[]
  away_lines: PlayerLine[]
  stats: { home: TeamStats; away: TeamStats } | null
}

export interface FormationSlot {
  id: string
  position: string
  x: number
  y: number
  default_role: string
}

export interface Formation {
  key: string
  name: string
  slots: FormationSlot[]
}

export interface RoleOption {
  key: string
  name: string
  group: string
  description: string
}

export interface InstructionOption {
  key: string
  label: string
  options: string[]
  default: string
}

export interface SheetEntry {
  slot: string | null
  position: string
  role: string
  player_id: number
  name: string
  number: number
  rating: number
  condition: number
}

export interface Tactics {
  formation: string
  roles: Record<string, string>
  lineup: Record<string, number> | null
  instructions: Record<string, string>
  starters: SheetEntry[]
  bench: SheetEntry[]
  formations: Formation[]
  roles_by_group: Record<string, RoleOption[]>
  instruction_options: InstructionOption[]
}

export interface TacticsUpdate {
  formation: string
  roles: Record<string, string>
  lineup: Record<string, number> | null
  instructions: Record<string, string>
}

export interface CupTie {
  tie: string
  home: ClubRef // drawn first
  away: ClubRef | null // null: a bye
  fixtures: Fixture[]
  winner: ClubRef | null
}

export interface CupRound {
  index: number
  name: string
  dates: string[]
  legs: number
  drawn: boolean
  ties: CupTie[]
}

export interface Cup {
  key: string
  name: string
  season: string
  rounds: CupRound[]
  winner: ClubRef | null
}

export interface CupSummary {
  key: string
  name: string
  current_round: string | null
  user_status: string | null
  winner: ClubRef | null
}

export interface CupRun {
  key: string
  name: string
  reached: string
  won: boolean
  out: boolean
}
