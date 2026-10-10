// Messages of the live match WebSocket (protocol v2, see backend/src/footsim/api/live.py).

import type { PlayerInfo } from './draw'

export interface ClockInfo {
  period: number
  display: string
  label: string
  state: 'playing' | 'break' | 'finished'
  added: number | null
  elapsed: number
}

export interface FeedItem {
  t: number
  minute: number
  clock: string
  period: number
  second: number
  type: string
  team: number | null
  text: string
}

// A goal the picture is holding on (LiveSession: the timeline stops for a few seconds).
export interface GoalInfo {
  t: number
  team: number
  scorer: string | null
  assist: string | null
  own_goal: boolean
  penalty: boolean
  clock: string | null
  score: [number, number]
}

// A player on the pitch: ability (ovr) and today's performance (rating) are different things.
export interface PlayerStatus {
  index: number
  team: number
  player_id: number
  name: string
  short_name: string
  number: number
  position: string
  slot: string // the formation slot he fills
  role: string
  active: boolean
  ovr: number
  rating: number
  energy: number
  condition: number
  yellow: number
  red: boolean
  roles?: RoleOption[] // the user's players on the pitch: each role of his position, best first
  goals: number
  assists: number
  shots: number
  on_target: number
  passes: number
  pass_pct: number | null
  tackles: number
  interceptions: number
  fouls: number
  saves: number
  xg: number
  minutes: number
}

export interface BenchStatus {
  player_id: number
  name: string
  short_name: string
  number: number
  position: string
  ovr: number
  condition: number
  age: number
  positions: string[]
  fit?: Record<string, number> // OVR if he replaced the player with this id
}

export interface RoleOption {
  key: string
  name: string
  ovr: number
}

// A substitution not made yet. ``staged``: chosen while paused or at a break, made when play goes on.
// Otherwise it waits for the next stoppage. Either can be called off.
export interface PendingSub {
  out: number
  in: number
  role: string | null
  staged: boolean
  roles?: RoleOption[] // the user's: roles the newcomer could play in the outgoing player's position
}

export interface Status {
  players: PlayerStatus[]
  bench: BenchStatus[][]
  vacant_slots?: { id: string; position: string }[] // the user's formation slots with no player
}

export interface LiveState {
  teams: { name: string; club_id: number }[]
  userTeam: number
  score: [number, number]
  t: number
  shown: number // the match time the picture should be showing
  holding: GoalInfo | null // the picture is holding on this goal
  clock: ClockInfo
  paused: boolean
  speed: number
  speeds: number[]
  rate: number // match seconds per real second
  playRate: number // the same on screen: a highlight is replayed no faster than its own rate
  mode: string
  finished: boolean
  atBreak: boolean
  restart: { kind: string; variant: string; team: number } | null
  pendingSubs: PendingSub[][]
  subsLeft: [number, number]
  lineup: PlayerInfo[]
  formation: string[]
  formations: { key: string; name: string; slots?: { id: string; position: string; x: number; y: number }[] }[]
  instructions: Record<string, string>[]
  instructionOptions: { key: string; label: string; options: string[] }[]
  autoSubs: boolean[]
  aiManager: boolean[] // the AI manager adjusts that side's tactics during the match
  stats: Record<string, number[]>
  feed: FeedItem[]
  status: Status
}

// The engine's debug snapshot (sent only while the viewer asks for it; see
// MatchEngine.debug_snapshot). Positions are pitch metres; players by engine index.
export interface DebugTeam {
  phase?: string
  attacking?: boolean
  width?: number
  back?: number // x of the back line
  mid?: number | null // x of the midfield line, out of possession
  front?: number // x of the front line
  pressers?: number[]
  offside?: number | null // x of the offside line this team attacks against
}

export interface DebugOption {
  kind: string
  utility: number
  target: [number, number] | null
  estimate: number | null // the passer's estimated chance of success
  chosen: boolean
}

export interface DebugSnapshot {
  t: number
  tick: number
  clock: string
  state: string
  owner: number
  restart: { kind: string; variant: string; team: number; taker: number | null; wait: number } | null
  teams: DebugTeam[]
  targets: number[] // x0, y0, x1, y1, ...
  urgent: number[]
  running: number[]
  stamina: number[]
  decision: { t: number; player: number; options: DebugOption[] } | null
  instructions: Record<string, string>[]
}

/** The role key of a player on the pitch (status gives its name). */
export function currentRoleKey(p: PlayerStatus): string | undefined {
  return p.roles?.find((r) => r.name === p.role)?.key
}
