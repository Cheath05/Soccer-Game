// Connection to a live match: keeps the latest state and a buffer of engine frames that the
// pitch view plays back at the match's rate (see PitchView).

import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { MutableRefObject } from 'react'

import { toSnapshot } from './draw'
import type { Snapshot } from './draw'
import type { DebugSnapshot, LiveState } from './protocol'

// The server's word on what should be on screen: match time ``shown`` at ``wall``
// (performance.now()), moving on at ``rate`` match seconds per real second unless stopped.
export interface Sync {
  shown: number
  wall: number
  rate: number
  moving: boolean
  holdAt: number | null // the picture stops here (a goal) until the server moves it on
}

export interface LiveMatch {
  live: LiveState | null
  liveRef: MutableRefObject<LiveState | null>
  buffer: MutableRefObject<Snapshot[]>
  debugBuffer: MutableRefObject<DebugSnapshot[]> // only while the debug overlay is on
  playhead: MutableRefObject<number | null>
  sync: MutableRefObject<Sync | null>
  error: string | null // the match can't be shown
  notice: string | null // a command was refused
  ended: [number, number] | null
  send: (message: Record<string, unknown>) => void
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Message = Record<string, any>

function fromInit(msg: Message): LiveState {
  return {
    teams: msg.teams,
    userTeam: msg.user_team,
    score: msg.score,
    t: msg.t,
    shown: msg.shown ?? msg.t,
    holding: msg.holding ?? null,
    clock: msg.clock,
    paused: msg.paused,
    speed: msg.speed,
    speeds: msg.speeds,
    rate: msg.rate,
    playRate: msg.play_rate ?? msg.rate,
    mode: msg.mode,
    finished: msg.finished,
    atBreak: msg.at_break,
    restart: msg.restart,
    pendingSubs: msg.pending_subs,
    subsLeft: msg.subs_left,
    lineup: msg.lineup,
    formation: msg.formation,
    formations: msg.formations,
    instructions: msg.instructions,
    instructionOptions: msg.instruction_options,
    autoSubs: msg.auto_subs,
    aiManager: msg.ai_manager ?? [false, false], // older servers don't send it
    stats: msg.stats,
    feed: [...msg.feed].reverse(),
    status: msg.status,
  }
}

// ``offset`` is the server clock's lag behind ours in seconds (the smallest seen): with it,
// ``shown`` is placed at the moment the server meant, not when its message happened to arrive.
function toSync(msg: Message, offset: number): Sync | null {
  if (typeof msg.shown !== 'number') return null // an older server: free-running playback
  const wall = typeof msg.server_time === 'number' && Number.isFinite(offset) ? (msg.server_time + offset) * 1000 : performance.now()
  return {
    shown: msg.shown,
    wall,
    rate: msg.play_rate ?? msg.rate,
    moving: (!msg.paused || msg.at_break || msg.finished) && !msg.holding,
    holdAt: msg.hold_at ?? null,
  }
}

export function useLiveMatch(fixtureId: string): LiveMatch {
  const queryClient = useQueryClient()
  const wsRef = useRef<WebSocket | null>(null)
  const liveRef = useRef<LiveState | null>(null)
  const buffer = useRef<Snapshot[]>([])
  const debugBuffer = useRef<DebugSnapshot[]>([])
  const playhead = useRef<number | null>(null)
  const sync = useRef<Sync | null>(null)
  const clockOffset = useRef(Infinity)
  const nextId = useRef(1)
  const [live, setLive] = useState<LiveState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [ended, setEnded] = useState<[number, number] | null>(null)

  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(null), 4000)
    return () => window.clearTimeout(timer)
  }, [notice])

  const send = useCallback((message: Record<string, unknown>) => {
    wsRef.current?.send(JSON.stringify({ ...message, cmd_id: nextId.current++ }))
  }, [])

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${protocol}://${window.location.host}/api/fixtures/${fixtureId}/live`)
    wsRef.current = ws
    const commit = (next: LiveState) => {
      liveRef.current = next
      setLive(next)
    }
    clockOffset.current = Infinity
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data as string) as Message
      if (typeof msg.server_time === 'number') {
        clockOffset.current = Math.min(clockOffset.current, performance.now() / 1000 - msg.server_time)
      }
      if (msg.type === 'ack') return
      if (msg.type === 'error') {
        // A refused command is shown briefly; a failure without a command ends the view.
        if (msg.cmd_id == null) setError(msg.message)
        else setNotice(msg.message)
        return
      }
      if (msg.type === 'end') {
        setEnded(msg.score)
        const previous = liveRef.current
        if (previous) {
          commit({
            ...previous,
            score: msg.score,
            stats: msg.stats ?? previous.stats,
            clock: msg.clock ?? previous.clock,
            status: msg.status ?? previous.status,
            finished: true,
            paused: true,
          })
        }
        void queryClient.invalidateQueries()
        return
      }
      if (msg.type === 'init') {
        const state = fromInit(msg)
        buffer.current = (msg.frames as number[][]).map(toSnapshot)
        debugBuffer.current = []
        sync.current = toSync(msg, clockOffset.current)
        playhead.current =
          sync.current?.shown ?? (buffer.current.length ? buffer.current[buffer.current.length - 1].t : null)
        commit(state)
        return
      }
      const previous = liveRef.current
      if (!previous) return
      const next: LiveState = {
        ...previous,
        score: msg.score,
        t: msg.t,
        shown: msg.shown ?? msg.t,
        holding: msg.holding ?? null,
        clock: msg.clock,
        paused: msg.paused,
        speed: msg.speed,
        rate: msg.rate,
        playRate: msg.play_rate ?? msg.rate,
        mode: msg.mode,
        finished: msg.finished,
        atBreak: msg.at_break,
        restart: msg.restart,
        pendingSubs: msg.pending_subs,
        subsLeft: msg.subs_left,
      }
      sync.current = toSync(msg, clockOffset.current)
      if (msg.feed) next.feed = [...[...msg.feed].reverse(), ...previous.feed].slice(0, 250)
      if (msg.lineup) next.lineup = msg.lineup
      if (msg.formation) next.formation = msg.formation
      if (msg.stats) next.stats = msg.stats
      if (msg.status) next.status = msg.status
      if (msg.instructions) next.instructions = msg.instructions
      if (msg.auto_subs) next.autoSubs = msg.auto_subs
      if (msg.ai_manager) next.aiManager = msg.ai_manager
      if (msg.lineup_stamina) {
        next.lineup = next.lineup.map((p) => ({ ...p, stamina: msg.lineup_stamina[p.index] }))
      }
      if (msg.debug) {
        // Updates keep coming while paused: keep a snapshot only when the match has moved on.
        const snapshot = msg.debug as DebugSnapshot
        const newest = debugBuffer.current[debugBuffer.current.length - 1]
        if (!newest || snapshot.t > newest.t) debugBuffer.current.push(snapshot)
        if (debugBuffer.current.length > 400) debugBuffer.current.splice(0, debugBuffer.current.length - 400)
      }
      const frames = (msg.frames as number[][]).map(toSnapshot)
      if (frames.length) {
        const last = buffer.current[buffer.current.length - 1]
        const fresh = last ? frames.filter((f) => f.t > last.t) : frames
        if (msg.highlight || (last && fresh.length && fresh[0].t - last.t > 3)) {
          buffer.current = fresh // a highlight or a jump: play on from it
          playhead.current = fresh.length ? fresh[0].t : playhead.current
          const from = fresh.length ? fresh[0].t : Infinity
          debugBuffer.current = debugBuffer.current.filter((d) => d.t >= from)
        } else {
          buffer.current.push(...fresh)
        }
      }
      commit(next)
    }
    ws.onerror = () => setError('Lost connection to the match.')
    return () => ws.close()
  }, [fixtureId, queryClient])

  return { live, liveRef, buffer, debugBuffer, playhead, sync, error, notice, ended, send }
}
