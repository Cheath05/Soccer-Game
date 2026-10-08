// Mirrors backend/src/footsim/api/schemas.py.

export interface Health {
  status: string
  version: string // MAJOR.MINOR ("1.12"); a server that predates version numbers sends the package's own, with no package_version
  package_version?: string
  saves_dir: string
  default_saves: boolean
  // The build the server runs. A server that predates these omits them.
  commit?: string // short hash, or "unknown"
  commit_date?: string // ISO 8601
  branch?: string
  dirty?: boolean // tracked files have changed since that commit
}

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
  review?: SeasonReview | null // how the season went across the game, and for the squad
  news?: string[] // the sim's other news: what the review doesn't cover
}

/** A competition's winners at a season's end: a league's champions or a cup's. (Play-off winners
 * are among the promoted clubs, not champions.) */
export interface Honour {
  kind: 'league' | 'cup'
  key: string
  name: string
  nation: string // a nation code such as ENG
  tier: number // a league's; 0 for a cup
  winner: ClubRef
}

/** A notable result of the season: a major league's champions, a cup upset. Continental titles
 * will be another kind. */
export interface Headline {
  kind: 'league_title' | 'cup_upset' | 'continental_title'
  text: string
  club: ClubRef
  competition: string
  nation: string
  detail: string | null
}

/** A club going up or down a league at the season's end. */
export interface ClubMove {
  club: ClubRef
  nation: string
  from_league: string
  to_league: string
  position: number | null // where it finished in the league it left
  via_playoffs: boolean
}

/** One of the user's players whose overall changed over the season. */
export interface Development {
  player_id: number
  name: string
  position: string
  age: number
  before: number // his overall as the season began
  after: number // and as it ended
  change: number
}

export interface Retirement {
  player_id: number
  name: string
  position: string
  age: number
  overall: number
  club: ClubRef | null
  own_player: boolean
}

export interface YouthIntake {
  player_id: number
  name: string
  position: string
  age: number
  overall: number
  potential: { low: number; high: number; label: string }
}

export interface SeasonReview {
  season: string
  next_season: string | null
  honours: Honour[]
  headlines?: Headline[] // notable results, shown first in the other news
  promoted: ClubMove[]
  relegated: ClubMove[]
  development: Development[] // best improvement first
  development_recorded: boolean // false: the season began before the game kept the record
  development_since: string | null // the day it began being kept, when that was after the start
  retired: Retirement[]
  youth: YouthIntake[]
}

export interface SimStatus {
  running: boolean
  start: string
  until: string
  date: string // how far it has got
  results: SimResult[]
  messages: string[]
  stop: 'date' | 'season_end' | 'offer' | 'cancelled' | 'abandoned' | 'error' | null
  error: string | null
  season_final?: SeasonFinal | null // when it stopped at the season's end
}

export interface AdvanceResult {
  date: string
  stop: 'match' | 'season_end' | 'offer' | 'limit'
  fixture_id: number | null
  messages: string[]
  season_final?: SeasonFinal | null // when it stopped at the season's end
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
  started?: boolean // a match has been played (a server that predates it omits it)
  first_match?: string | null // the date of its first league match
  rows: TableRow[]
}

export type Outcome = 'champion' | 'promoted' | 'playoff_winner' | 'playoffs' | 'relegated'

export interface Season {
  id: number
  label: string
  current: boolean
  finished?: boolean // its league tables are final (a server that predates it omits it)
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
  season_start_overall?: number | null // his overall as this season began; null if not recorded
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
  budget_eur: number // for transfer fees and new wages this season; rounded for other clubs
  balance_eur: number
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

/** A player's season in one competition (or, on a total row, in all of them). */
export interface PlayerSeasonLine {
  club: ClubRef | null // null on a total row
  competition_key: string
  competition: string
  appearances: number // starts and substitute appearances
  starts: number
  minutes: number
  goals: number
  assists: number
  average_rating: number | null
  yellow: number
  red: number
}

export interface PlayerSeason {
  season_id: number
  season: string
  lines: PlayerSeasonLine[]
  total: PlayerSeasonLine
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

/** Why a starter rates what he does in his slot: kind is role, position or condition; delta is in rating points. */
export interface RatingAdjustment {
  kind: string
  label: string
  delta: number
}

/** A starter (slot set), a substitute or a reserve. A starter's rating is his slot rating; overall plus adjustments make it. */
export interface SheetEntry {
  slot: string | null
  position: string
  role: string
  player_id: number
  name: string
  number: number
  rating: number
  condition: number
  overall: number
  best_position: string
  positions: string[]
  familiarity: number
  position_fit: 'natural' | 'adjusted' | 'out'
  role_name: string
  adjustments: RatingAdjustment[]
  available: boolean
}

export interface Tactics {
  formation: string
  roles: Record<string, string>
  lineup: Record<string, number> | null
  instructions: Record<string, string>
  starters: SheetEntry[]
  bench: SheetEntry[]
  reserves: SheetEntry[]
  bench_chosen: boolean
  bench_size: number
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
  nation?: string // a nation code such as ENG; a server that predates it omits it (and had only England's cups)
  season: string
  rounds: CupRound[]
  winner: ClubRef | null
}

export interface CupSummary {
  key: string
  name: string
  nation?: string // the country it is played in, as on Cup
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

/** A month of the club's recurring money at today's rates: income positive, costs negative, and
 * the profit their sum. */
export interface Monthly {
  tv_eur: number // its share of its league's TV money
  commercial_eur: number // commercial and matchday
  wages_eur: number
  running_eur: number
  profit_eur: number
}

/** A part of the month that changed from one settlement to the next (a month's worth each; a
 * cost is negative). `date` is the settlement it first showed in. */
export interface FinanceChange {
  date: string
  label: string
  before_eur: number
  after_eur: number
}

/** One-off money: the opening balance, a transfer, prize money, a parachute payment. */
export interface Transaction {
  date: string
  kind: string
  label: string
  amount_eur: number
}

export interface Board {
  target: number | null
  position: number | null
  played: number
  league_size: number | null
  confidence: number | null
  mood: string
}

export interface Finances {
  club: ClubRef
  season: string
  league: string | null
  balance_eur: number
  budget_eur: number // for transfer fees and new wages this season
  wage_bill_weekly_eur: number
  wage_capacity_weekly_eur: number // the weekly wage bill the club's income supports
  wage_room_weekly_eur: number // what the budget could still pay a week, to the season's end
  monthly: Monthly
  season_profit_so_far_eur: number
  changes: FinanceChange[] // the latest first
  transactions: Transaction[] // the latest first
  board_enabled: boolean
  board: Board | null // null when the board is off
}

// GET /api/calendar: the user's fixtures, window days and breaks in a date range.
export interface CalendarData {
  start: string
  end: string
  today: string
  season_start: string
  season_end: string
  fixtures: Fixture[]
  window_days: string[]
  international_breaks: { start: string; end: string }[]
}
