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

// A player on the pitch: ability (ovr) and today's performance (rating) are different things.
export interface PlayerStatus {
  index: number
  team: number
  player_id: number
  name: string
  short_name: string
  number: number
  position: string
  role: string
  active: boolean
  ovr: number
  rating: number
  energy: number
  condition: number
  yellow: number
  red: boolean
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

export interface Status {
  players: PlayerStatus[]
  bench: BenchStatus[][]
}

export interface LiveState {
  teams: { name: string; club_id: number }[]
  userTeam: number
  score: [number, number]
  t: number
  clock: ClockInfo
  paused: boolean
  speed: number
  speeds: number[]
  rate: number // match seconds per real second
  mode: string
  finished: boolean
  atBreak: boolean
  restart: { kind: string; variant: string; team: number } | null
  pendingSubs: { out: number; in: number }[][]
  subsLeft: [number, number]
  lineup: PlayerInfo[]
  formation: string[]
  formations: { key: string; name: string }[]
  instructions: Record<string, string>[]
  instructionOptions: { key: string; label: string; options: string[] }[]
  autoSubs: boolean[]
  aiManager: boolean[] // the AI manager adjusts that side's tactics during the match
  stats: Record<string, number[]>
  feed: FeedItem[]
  status: Status
}
