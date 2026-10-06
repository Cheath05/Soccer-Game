// Canvas drawing for the 2D match viewer. The viewer contains no football logic: it only
// draws the positions the engine produced (see backend/src/footsim/match/engine).

import type { DebugSnapshot } from './protocol'

export const PITCH_LENGTH = 105
export const PITCH_WIDTH = 68

export interface PlayerInfo {
  index: number
  team: number
  name: string
  number: number
  position: string
  player_id: number
  active: boolean
  stamina: number
}

export interface Snapshot {
  t: number
  ball: [number, number, number]
  owner: number
  players: Float32Array // x0, y0, x1, y1, ...
}

export const TEAM_COLORS = [
  { shirt: '#1c7ed6', text: '#ffffff', keeper: '#40c057' },
  { shirt: '#e8590c', text: '#ffffff', keeper: '#fab005' },
]

export function toSnapshot(frame: number[]): Snapshot {
  return {
    t: frame[0],
    ball: [frame[1], frame[2], frame[3]],
    owner: frame[4],
    players: Float32Array.from(frame.slice(5)),
  }
}

export function interpolate(a: Snapshot, b: Snapshot, t: number): Snapshot {
  const span = b.t - a.t
  const k = span > 0 ? Math.min(1, Math.max(0, (t - a.t) / span)) : 1
  const players = new Float32Array(a.players.length)
  for (let i = 0; i < players.length; i++) {
    // Teleports (restarts, substitutions) snap instead of sliding across the pitch.
    const jump = Math.abs(b.players[i] - a.players[i]) > 8
    players[i] = jump ? b.players[i] : a.players[i] + (b.players[i] - a.players[i]) * k
  }
  const ball: [number, number, number] = [
    a.ball[0] + (b.ball[0] - a.ball[0]) * k,
    a.ball[1] + (b.ball[1] - a.ball[1]) * k,
    a.ball[2] + (b.ball[2] - a.ball[2]) * k,
  ]
  return { t, ball, owner: k < 0.5 ? a.owner : b.owner, players }
}

export function drawPitch(ctx: CanvasRenderingContext2D, scale: number, pad: number) {
  const w = PITCH_LENGTH * scale
  const h = PITCH_WIDTH * scale
  ctx.fillStyle = '#2f7d3b'
  ctx.fillRect(0, 0, w + pad * 2, h + pad * 2)
  for (let i = 0; i < 10; i += 2) {
    ctx.fillStyle = '#2b7437'
    ctx.fillRect(pad + (i * w) / 10, pad, w / 10, h)
  }
  ctx.save()
  ctx.translate(pad, pad)
  ctx.strokeStyle = 'rgba(255,255,255,0.8)'
  ctx.lineWidth = Math.max(1, scale * 0.15)
  ctx.strokeRect(0, 0, w, h)
  ctx.beginPath()
  ctx.moveTo(w / 2, 0)
  ctx.lineTo(w / 2, h)
  ctx.stroke()
  ctx.beginPath()
  ctx.arc(w / 2, h / 2, 9.15 * scale, 0, Math.PI * 2)
  ctx.stroke()
  for (const side of [0, 1]) {
    const x0 = side === 0 ? 0 : w
    const dir = side === 0 ? 1 : -1
    ctx.strokeRect(side === 0 ? 0 : w - 16.5 * scale, h / 2 - 20.16 * scale, 16.5 * scale, 40.32 * scale)
    ctx.strokeRect(side === 0 ? 0 : w - 5.5 * scale, h / 2 - 9.16 * scale, 5.5 * scale, 18.32 * scale)
    ctx.beginPath()
    ctx.arc(x0 + dir * 11 * scale, h / 2, scale * 0.35, 0, Math.PI * 2)
    ctx.fillStyle = 'white'
    ctx.fill()
    ctx.fillStyle = 'rgba(255,255,255,0.85)'
    ctx.fillRect(side === 0 ? -1.5 * scale : w, h / 2 - 3.66 * scale, 1.5 * scale, 7.32 * scale)
  }
  ctx.restore()
}

export function drawFrame(
  ctx: CanvasRenderingContext2D,
  scale: number,
  pad: number,
  snap: Snapshot,
  lineup: PlayerInfo[],
  showNames: boolean,
  selected: number | null = null,
) {
  ctx.save()
  ctx.translate(pad, pad)
  const radius = Math.max(5, scale * 1.15)
  for (const p of lineup) {
    if (!p.active) continue
    const x = snap.players[p.index * 2] * scale
    const y = snap.players[p.index * 2 + 1] * scale
    if (x < 0) continue
    const colors = TEAM_COLORS[p.team]
    if (p.index === selected) {
      ctx.beginPath()
      ctx.arc(x, y, radius * 1.8, 0, Math.PI * 2)
      ctx.strokeStyle = '#ffe066'
      ctx.lineWidth = 2
      ctx.stroke()
    }
    ctx.beginPath()
    ctx.arc(x, y, radius, 0, Math.PI * 2)
    ctx.fillStyle = p.position === 'GK' ? colors.keeper : colors.shirt
    ctx.fill()
    ctx.lineWidth = snap.owner === p.index ? 3 : 1.5
    ctx.strokeStyle = snap.owner === p.index ? '#ffe066' : 'rgba(0,0,0,0.5)'
    ctx.stroke()
    ctx.fillStyle = colors.text
    ctx.font = `bold ${Math.round(radius * 1.05)}px system-ui, sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(String(p.number), x, y + 0.5)
    if (showNames) {
      ctx.font = `${Math.max(9, Math.round(radius * 0.85))}px system-ui, sans-serif`
      ctx.fillStyle = 'rgba(255,255,255,0.9)'
      ctx.fillText(p.name, x, y + radius * 1.9)
    }
  }
  const [bx, by, bz] = snap.ball
  const lift = bz * scale * 0.6
  ctx.beginPath()
  ctx.ellipse(bx * scale, by * scale, scale * (0.45 + bz * 0.05), scale * (0.3 + bz * 0.03), 0, 0, Math.PI * 2)
  ctx.fillStyle = 'rgba(0,0,0,0.35)'
  ctx.fill()
  ctx.beginPath()
  ctx.arc(bx * scale, by * scale - lift, Math.max(3, scale * 0.5), 0, Math.PI * 2)
  ctx.fillStyle = '#ffffff'
  ctx.fill()
  ctx.strokeStyle = '#222'
  ctx.lineWidth = 1
  ctx.stroke()
  ctx.restore()
}

// --- debug overlay (?debug=1) -----------------------------------------------------------

/** The latest debug snapshot at or before match time ``t`` (the engine runs a little ahead
 * of the picture, so newer snapshots wait until the playhead reaches them). */
export function debugAt(buffer: DebugSnapshot[], t: number): DebugSnapshot | null {
  let found: DebugSnapshot | null = null
  for (const snap of buffer) {
    if (snap.t > t) break
    found = snap
  }
  return found
}

/** What the engine intends: team lines, each player's target, pressers, and the ball
 * carrier's options with their scores. */
export function drawDebug(
  ctx: CanvasRenderingContext2D,
  scale: number,
  pad: number,
  snap: Snapshot,
  dbg: DebugSnapshot,
  lineup: PlayerInfo[],
) {
  ctx.save()
  ctx.translate(pad, pad)
  const h = PITCH_WIDTH * scale
  const vertical = (x: number) => {
    ctx.beginPath()
    ctx.moveTo(x * scale, 0)
    ctx.lineTo(x * scale, h)
    ctx.stroke()
  }
  dbg.teams.forEach((team, t) => {
    if (team.back === undefined || team.front === undefined) return
    ctx.setLineDash([6, 4])
    ctx.lineWidth = 1.5
    ctx.strokeStyle = TEAM_COLORS[t].shirt
    vertical(team.back)
    if (team.mid != null) vertical(team.mid)
    vertical(team.front)
    if (team.offside != null) {
      ctx.setLineDash([2, 3])
      ctx.strokeStyle = 'rgba(255,255,255,0.75)'
      vertical(team.offside)
    }
  })
  ctx.setLineDash([])

  // Where each player is heading: red when he's sprinting.
  for (const p of lineup) {
    if (!p.active) continue
    const x = snap.players[p.index * 2] * scale
    const y = snap.players[p.index * 2 + 1] * scale
    const tx = dbg.targets[p.index * 2] * scale
    const ty = dbg.targets[p.index * 2 + 1] * scale
    if (x < 0 || Number.isNaN(tx)) continue
    const urgent = dbg.urgent.includes(p.index)
    ctx.strokeStyle = urgent ? 'rgba(255,90,90,0.95)' : 'rgba(255,255,255,0.5)'
    ctx.lineWidth = urgent ? 1.8 : 1
    ctx.beginPath()
    ctx.moveTo(x, y)
    ctx.lineTo(tx, ty)
    ctx.stroke()
    ctx.beginPath()
    ctx.arc(tx, ty, 2, 0, Math.PI * 2)
    ctx.fillStyle = ctx.strokeStyle
    ctx.fill()
    if (dbg.running.includes(p.index)) {
      ctx.fillStyle = '#ffe066'
      ctx.font = `bold ${Math.max(9, Math.round(scale * 1.1))}px system-ui, sans-serif`
      ctx.fillText('run', tx + 4, ty - 4)
    }
  }
  // Pressers: a yellow ring.
  for (const team of dbg.teams) {
    for (const i of team.pressers ?? []) {
      const x = snap.players[i * 2] * scale
      const y = snap.players[i * 2 + 1] * scale
      ctx.beginPath()
      ctx.arc(x, y, Math.max(8, scale * 2), 0, Math.PI * 2)
      ctx.strokeStyle = '#ffd43b'
      ctx.lineWidth = 2
      ctx.stroke()
    }
  }
  // The ball carrier's best options and the one he took.
  const decision = dbg.decision && dbg.decision.player === dbg.owner ? dbg.decision : null
  if (decision && decision.player >= 0) {
    const cx = snap.players[decision.player * 2] * scale
    const cy = snap.players[decision.player * 2 + 1] * scale
    ctx.font = `${Math.max(9, Math.round(scale * 1.05))}px ui-monospace, monospace`
    for (const option of decision.options) {
      if (!option.target) continue
      const [ox, oy] = [option.target[0] * scale, option.target[1] * scale]
      ctx.strokeStyle = option.chosen ? '#66d9e8' : 'rgba(102,217,232,0.4)'
      ctx.lineWidth = option.chosen ? 2 : 1
      ctx.beginPath()
      ctx.moveTo(cx, cy)
      ctx.lineTo(ox, oy)
      ctx.stroke()
      ctx.fillStyle = option.chosen ? '#66d9e8' : 'rgba(102,217,232,0.75)'
      const estimate = option.estimate != null ? ` ${Math.round(option.estimate * 100)}%` : ''
      ctx.fillText(`${option.kind} ${option.utility.toFixed(3)}${estimate}`, ox + 4, oy + 10)
    }
  }
  // Text panel.
  const byIndex = new Map(lineup.map((p) => [p.index, p]))
  const chosen = decision?.options.find((o) => o.chosen)
  const lines = [
    `${dbg.clock}  tick ${dbg.tick}  ${dbg.state}` +
      (dbg.restart ? `  ${dbg.restart.kind}${dbg.restart.variant ? `/${dbg.restart.variant}` : ''} ${dbg.restart.wait}s` : ''),
    ...dbg.teams.map(
      (team, t) =>
        `${t === 0 ? 'Home' : 'Away'} ${team.phase ?? '-'}  lines ${team.back?.toFixed(0) ?? '-'}-${team.mid != null ? `${team.mid.toFixed(0)}-` : ''}${team.front?.toFixed(0) ?? '-'}  ` +
        `width ${team.width?.toFixed(0) ?? '-'}  pressing ${team.pressers?.length ?? 0}`,
    ),
    decision && chosen
      ? `On the ball #${byIndex.get(decision.player)?.number ?? '?'}: ${chosen.kind} (${chosen.utility.toFixed(3)})`
      : 'On the ball: -',
  ]
  ctx.font = '11px ui-monospace, monospace'
  const width = Math.max(...lines.map((l) => ctx.measureText(l).width)) + 12
  ctx.fillStyle = 'rgba(0,0,0,0.6)'
  ctx.fillRect(4, 4, width, lines.length * 14 + 8)
  ctx.fillStyle = '#ffffff'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'top'
  lines.forEach((line, k) => ctx.fillText(line, 10, 9 + k * 14))
  ctx.restore()
}
