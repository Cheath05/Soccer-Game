// Canvas drawing for the 2D match viewer. The viewer contains no football logic: it only
// draws the positions the engine produced (see backend/src/footsim/match/engine).

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
