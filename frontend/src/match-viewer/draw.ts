// Canvas drawing for the 2D match viewer. The viewer contains no football logic: it only
// draws the positions the engine produced (see backend/src/footsim/match/engine).

import type { DebugSnapshot } from './protocol'

export const PITCH_LENGTH = 105
export const PITCH_WIDTH = 68
export const NET_DEPTH = 2.2 // metres the goal nets are drawn behind the goal line
const GOAL_WIDTH = 7.32

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
  { shirt: '#2f6fed', text: '#ffffff', keeper: '#8b5cf6', keeperText: '#ffffff' },
  { shirt: '#f4731c', text: '#ffffff', keeper: '#facc15', keeperText: '#1f2937' },
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

// --- the pitch ----------------------------------------------------------------------------

/** Pixels around the pitch: room for the nets behind the goal lines, and a little margin. */
export function padFor(scale: number): number {
  return Math.max(16, Math.round(scale * (NET_DEPTH + 0.6)))
}

/** The goal net behind one goal line (``side`` 0 is the left goal, 1 the right). With
 * ``frame`` it is the whole goal (posts, bar and mesh); without, just a faint mesh, which is
 * drawn over the ball so it can be seen inside the net. */
function drawNet(ctx: CanvasRenderingContext2D, scale: number, side: number, frame: boolean) {
  const w = PITCH_LENGTH * scale
  const h = PITCH_WIDTH * scale
  const depth = NET_DEPTH * scale
  const half = (GOAL_WIDTH / 2) * scale
  const x0 = side === 0 ? -depth : w
  const y0 = h / 2 - half
  ctx.save()
  ctx.beginPath()
  ctx.rect(x0, y0, depth, half * 2)
  if (frame) {
    ctx.fillStyle = 'rgba(255,255,255,0.10)'
    ctx.fill()
  }
  ctx.clip()
  ctx.strokeStyle = frame ? 'rgba(255,255,255,0.30)' : 'rgba(255,255,255,0.20)'
  ctx.lineWidth = 1
  const step = Math.max(3, scale * 0.55)
  ctx.beginPath()
  for (let x = x0; x <= x0 + depth + 0.5; x += step) {
    ctx.moveTo(x, y0)
    ctx.lineTo(x, y0 + half * 2)
  }
  for (let y = y0; y <= y0 + half * 2 + 0.5; y += step) {
    ctx.moveTo(x0, y)
    ctx.lineTo(x0 + depth, y)
  }
  ctx.stroke()
  ctx.restore()
  if (!frame) return
  // Posts and the back of the frame.
  ctx.strokeStyle = 'rgba(255,255,255,0.92)'
  ctx.lineWidth = Math.max(1.5, scale * 0.2)
  ctx.lineJoin = 'round'
  ctx.beginPath()
  const lineX = side === 0 ? 0 : w
  const backX = side === 0 ? -depth : w + depth
  ctx.moveTo(lineX, y0)
  ctx.lineTo(backX, y0)
  ctx.lineTo(backX, y0 + half * 2)
  ctx.lineTo(lineX, y0 + half * 2)
  ctx.stroke()
  ctx.fillStyle = '#ffffff'
  for (const y of [y0, y0 + half * 2]) {
    ctx.beginPath()
    ctx.arc(lineX, y, Math.max(2, scale * 0.24), 0, Math.PI * 2)
    ctx.fill()
  }
}

/** The goal nets again, faintly, over the ball: once the ball is in the net it reads as
 * being inside it. */
export function drawNetOverlay(ctx: CanvasRenderingContext2D, scale: number, pad: number) {
  ctx.save()
  ctx.translate(pad, pad)
  drawNet(ctx, scale, 0, false)
  drawNet(ctx, scale, 1, false)
  ctx.restore()
}

export function drawPitch(ctx: CanvasRenderingContext2D, scale: number, pad: number) {
  const w = PITCH_LENGTH * scale
  const h = PITCH_WIDTH * scale
  const full = { w: w + pad * 2, h: h + pad * 2 }
  // The ground around the pitch, slightly darker than the grass.
  const ground = ctx.createLinearGradient(0, 0, 0, full.h)
  ground.addColorStop(0, '#1d5a37')
  ground.addColorStop(1, '#174b2d')
  ctx.fillStyle = ground
  ctx.fillRect(0, 0, full.w, full.h)
  // Mown stripes along the length.
  const stripes = 14
  for (let i = 0; i < stripes; i++) {
    ctx.fillStyle = i % 2 === 0 ? '#2c7d4d' : '#33895a'
    ctx.fillRect(pad + (i * w) / stripes, pad, w / stripes + 0.5, h)
  }
  // Light falls off towards the corners.
  const light = ctx.createRadialGradient(pad + w / 2, pad + h / 2, h * 0.2, pad + w / 2, pad + h / 2, w * 0.62)
  light.addColorStop(0, 'rgba(255,255,255,0.05)')
  light.addColorStop(1, 'rgba(0,0,0,0.22)')
  ctx.fillStyle = light
  ctx.fillRect(pad, pad, w, h)

  ctx.save()
  ctx.translate(pad, pad)
  drawNet(ctx, scale, 0, true)
  drawNet(ctx, scale, 1, true)
  ctx.strokeStyle = 'rgba(255,255,255,0.78)'
  ctx.fillStyle = 'rgba(255,255,255,0.78)'
  ctx.lineWidth = Math.max(1.25, scale * 0.17)
  ctx.lineJoin = 'miter'
  ctx.strokeRect(0, 0, w, h)
  ctx.beginPath()
  ctx.moveTo(w / 2, 0)
  ctx.lineTo(w / 2, h)
  ctx.stroke()
  const spot = (x: number, y: number) => {
    ctx.beginPath()
    ctx.arc(x, y, Math.max(1.6, scale * 0.28), 0, Math.PI * 2)
    ctx.fill()
  }
  ctx.beginPath()
  ctx.arc(w / 2, h / 2, 9.15 * scale, 0, Math.PI * 2)
  ctx.stroke()
  spot(w / 2, h / 2)
  const arc = Math.acos((16.5 - 11) / 9.15) // the penalty arc, outside the box
  for (const side of [0, 1]) {
    const dir = side === 0 ? 1 : -1
    const x0 = side === 0 ? 0 : w
    ctx.strokeRect(side === 0 ? 0 : w - 16.5 * scale, h / 2 - 20.16 * scale, 16.5 * scale, 40.32 * scale)
    ctx.strokeRect(side === 0 ? 0 : w - 5.5 * scale, h / 2 - 9.16 * scale, 5.5 * scale, 18.32 * scale)
    spot(x0 + dir * 11 * scale, h / 2)
    ctx.beginPath()
    if (side === 0) ctx.arc(11 * scale, h / 2, 9.15 * scale, -arc, arc)
    else ctx.arc(w - 11 * scale, h / 2, 9.15 * scale, Math.PI - arc, Math.PI + arc)
    ctx.stroke()
  }
  for (const [cx, cy, from] of [
    [0, 0, 0],
    [w, 0, 0.5],
    [w, h, 1],
    [0, h, 1.5],
  ] as const) {
    ctx.beginPath()
    ctx.arc(cx, cy, scale, from * Math.PI, (from + 0.5) * Math.PI)
    ctx.stroke()
  }
  ctx.restore()
}

// --- players and the ball -----------------------------------------------------------------

function pentagon(ctx: CanvasRenderingContext2D, x: number, y: number, r: number, turn: number) {
  ctx.beginPath()
  for (let k = 0; k < 5; k++) {
    const a = turn + (k * 2 * Math.PI) / 5
    const px = x + Math.cos(a) * r
    const py = y + Math.sin(a) * r
    if (k === 0) ctx.moveTo(px, py)
    else ctx.lineTo(px, py)
  }
  ctx.closePath()
}

/** The ball: white with dark panels and a dark outline so it shows against the white lines as
 * well as the grass, a soft shadow on the ground and a lift when it is in the air. */
function drawBall(ctx: CanvasRenderingContext2D, scale: number, ball: [number, number, number]) {
  const [bx, by, bz] = ball
  const r = Math.max(5, scale * 0.62)
  const gx = bx * scale
  const gy = by * scale
  const height = Math.min(Math.max(bz, 0), 8)
  const lift = height * scale * 0.55
  // Shadow on the ground: smaller and fainter the higher the ball is.
  const fade = 1 / (1 + height * 0.35)
  ctx.save()
  ctx.translate(gx + lift * 0.1, gy + r * 0.35)
  ctx.scale(1, 0.5)
  const shadow = ctx.createRadialGradient(0, 0, 0, 0, 0, r * 1.7 * (1 + height * 0.05))
  shadow.addColorStop(0, `rgba(0,0,0,${0.55 * fade})`)
  shadow.addColorStop(1, 'rgba(0,0,0,0)')
  ctx.fillStyle = shadow
  ctx.beginPath()
  ctx.arc(0, 0, r * 1.7 * (1 + height * 0.05), 0, Math.PI * 2)
  ctx.fill()
  ctx.restore()
  // The ball itself, turning as it travels.
  ctx.save()
  ctx.translate(gx, gy - lift)
  ctx.rotate((bx + by * 0.6) / 0.35)
  const body = ctx.createRadialGradient(-r * 0.35, -r * 0.4, r * 0.1, 0, 0, r)
  body.addColorStop(0, '#ffffff')
  body.addColorStop(1, '#dfe4ea')
  ctx.beginPath()
  ctx.arc(0, 0, r, 0, Math.PI * 2)
  ctx.fillStyle = body
  ctx.fill()
  ctx.save()
  ctx.clip()
  ctx.fillStyle = '#1b2430'
  ctx.strokeStyle = '#1b2430'
  ctx.lineWidth = Math.max(0.6, r * 0.08)
  pentagon(ctx, 0, 0, r * 0.42, -Math.PI / 2)
  ctx.fill()
  for (let k = 0; k < 5; k++) {
    const a = -Math.PI / 2 + (k * 2 * Math.PI) / 5
    ctx.beginPath()
    ctx.moveTo(Math.cos(a) * r * 0.42, Math.sin(a) * r * 0.42)
    ctx.lineTo(Math.cos(a) * r * 0.78, Math.sin(a) * r * 0.78)
    ctx.stroke()
    pentagon(ctx, Math.cos(a) * r * 1.08, Math.sin(a) * r * 1.08, r * 0.42, a + Math.PI)
    ctx.fill()
  }
  ctx.restore()
  ctx.beginPath()
  ctx.arc(0, 0, r, 0, Math.PI * 2)
  ctx.lineWidth = Math.max(1.4, r * 0.2)
  ctx.strokeStyle = '#0f172a'
  ctx.stroke()
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
  const radius = Math.min(14, Math.max(7, scale * 1.2))
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.lineJoin = 'round'
  // Shadows first, so no marker's shadow falls on another marker.
  ctx.fillStyle = 'rgba(0,0,0,0.26)'
  for (const p of lineup) {
    if (!p.active) continue
    const x = snap.players[p.index * 2] * scale
    const y = snap.players[p.index * 2 + 1] * scale
    if (x < 0) continue
    ctx.beginPath()
    ctx.ellipse(x + radius * 0.15, y + radius * 0.6, radius * 1.05, radius * 0.6, 0, 0, Math.PI * 2)
    ctx.fill()
  }
  for (const p of lineup) {
    if (!p.active) continue
    const x = snap.players[p.index * 2] * scale
    const y = snap.players[p.index * 2 + 1] * scale
    if (x < 0) continue
    const colors = TEAM_COLORS[p.team]
    const keeper = p.position === 'GK'
    if (p.index === selected) {
      ctx.beginPath()
      ctx.arc(x, y, radius * 1.75, 0, Math.PI * 2)
      ctx.fillStyle = 'rgba(253,224,71,0.20)'
      ctx.fill()
      ctx.strokeStyle = '#fde047'
      ctx.lineWidth = 2
      ctx.stroke()
    }
    const owner = snap.owner === p.index
    if (owner) {
      ctx.beginPath()
      ctx.arc(x, y, radius + 3.5, 0, Math.PI * 2)
      ctx.strokeStyle = 'rgba(253,224,71,0.95)'
      ctx.lineWidth = 2.2
      ctx.stroke()
    }
    ctx.beginPath()
    ctx.arc(x, y, radius, 0, Math.PI * 2)
    ctx.fillStyle = keeper ? colors.keeper : colors.shirt
    ctx.fill()
    ctx.lineWidth = 1.8
    ctx.strokeStyle = 'rgba(255,255,255,0.95)'
    ctx.stroke()
    const text = keeper ? colors.keeperText : colors.text
    ctx.font = `700 ${Math.round(Math.max(8, radius * 1.1))}px system-ui, -apple-system, 'Segoe UI', sans-serif`
    if (text === '#ffffff') {
      ctx.lineWidth = 2.5
      ctx.strokeStyle = 'rgba(0,0,0,0.35)'
      ctx.strokeText(String(p.number), x, y + 0.5)
    }
    ctx.fillStyle = text
    ctx.fillText(String(p.number), x, y + 0.5)
  }
  if (showNames) {
    ctx.font = `600 ${Math.max(9, Math.round(radius * 0.8))}px system-ui, -apple-system, 'Segoe UI', sans-serif`
    for (const p of lineup) {
      if (!p.active) continue
      const x = snap.players[p.index * 2] * scale
      const y = snap.players[p.index * 2 + 1] * scale
      if (x < 0) continue
      const width = ctx.measureText(p.name).width + 8
      const height = Math.max(12, radius * 1.15)
      const top = y + radius + 3
      ctx.fillStyle = 'rgba(10,18,28,0.62)'
      ctx.beginPath()
      ctx.roundRect(x - width / 2, top, width, height, height / 2)
      ctx.fill()
      ctx.fillStyle = '#f8fafc'
      ctx.fillText(p.name, x, top + height / 2 + 0.5)
    }
  }
  drawBall(ctx, scale, snap.ball)
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
