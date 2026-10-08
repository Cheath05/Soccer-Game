import { Badge, Box, Group, Text } from '@mantine/core'
import { useState } from 'react'

import { matchRatingColor } from '../lib/format'
import type { BenchStatus, PlayerStatus } from './protocol'
import type { LiveMatch } from './useLiveMatch'

const W = 330
const H = 400

/** Where a slot's disc sits (the formation's coordinates, own goal at the bottom). */
function place(slot: { x: number; y: number }) {
  return { left: slot.y * (W - 56) + 28, top: 30 + (1 - (slot.x - 0.02) / 0.76) * (H - 64) }
}

function energyColor(value: number): string {
  return value > 75 ? '#12b886' : value > 60 ? '#fab005' : '#fa5252'
}

type Drag = { kind: 'pitch' | 'bench'; id: number }

/** The user's side in formation. Drag a substitute onto a player to bring him on for him, a player onto a
 * substitute likewise, or one player onto another to swap their positions. */
export default function SubsPitch({ match, onInspect }: { match: LiveMatch; onInspect: (index: number) => void }) {
  const { live, send } = match
  const [drag, setDrag] = useState<Drag | null>(null)
  const [over, setOver] = useState<string | null>(null)
  if (!live) return null
  const team = live.userTeam
  const shape = live.formations.find((f) => f.key === live.formation[team])
  const players = live.status.players.filter((p) => p.team === team && p.active)
  const bySlot = new Map(players.map((p) => [p.slot, p]))
  const bench: BenchStatus[] = live.status.bench[team] ?? []
  const waiting = live.pendingSubs?.[team] ?? []
  const leaving = new Set(waiting.map((w) => w.out))
  const coming = new Set(waiting.map((w) => w.in))
  const canSub = live.subsLeft[team] > 0 && !live.finished
  if (!shape?.slots) return null

  const finish = () => {
    setDrag(null)
    setOver(null)
  }
  const dropOnPlayer = (target: PlayerStatus) => {
    const dragged = drag
    finish()
    if (!dragged || (dragged.kind === 'pitch' && dragged.id === target.player_id)) return
    if (dragged.kind === 'bench') {
      if (canSub && !leaving.has(target.player_id)) send({ type: 'sub', out: target.player_id, in: dragged.id })
    } else {
      send({ type: 'swap', a: dragged.id, b: target.player_id })
    }
  }
  const dropOnBench = (sub: BenchStatus) => {
    const dragged = drag
    finish()
    if (dragged?.kind === 'pitch' && canSub && !coming.has(sub.player_id) && !leaving.has(dragged.id)) {
      send({ type: 'sub', out: dragged.id, in: sub.player_id })
    }
  }
  const dragStart = (e: React.DragEvent, d: Drag) => {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(d.id))
    setDrag(d)
  }
  const keeperSwap = (target: PlayerStatus) =>
    drag?.kind === 'pitch' && (target.position === 'GK' || players.find((p) => p.player_id === drag.id)?.position === 'GK')
  const droppable = (target: PlayerStatus) =>
    drag != null && !(drag.kind === 'pitch' && (drag.id === target.player_id || keeperSwap(target))) && !(drag.kind === 'bench' && !canSub)

  return (
    <Box>
      <Box pos="relative" w={W} h={H} mx="auto" style={{ borderRadius: 8, overflow: 'hidden' }}>
        <svg width={W} height={H} style={{ position: 'absolute', inset: 0 }}>
          <rect width={W} height={H} fill="#2f7d3b" />
          {Array.from({ length: 8 }, (_, i) => (
            <rect key={i} y={(i * H) / 8} width={W} height={H / 16} fill="#2c7437" />
          ))}
          <g stroke="rgba(255,255,255,0.7)" strokeWidth={2} fill="none">
            <rect x={6} y={6} width={W - 12} height={H - 12} />
            <line x1={6} y1={H / 2} x2={W - 6} y2={H / 2} />
            <circle cx={W / 2} cy={H / 2} r={34} />
            <rect x={W * 0.2} y={6} width={W * 0.6} height={H * 0.16} />
            <rect x={W * 0.2} y={H - 6 - H * 0.16} width={W * 0.6} height={H * 0.16} />
          </g>
        </svg>
        {shape.slots.map((slot) => {
          const p = bySlot.get(slot.id)
          const { left, top } = place(slot)
          if (!p) return null
          const target = over === `p${p.player_id}` && droppable(p)
          const ring = target ? '#ffd43b' : leaving.has(p.player_id) ? '#fd7e14' : 'white'
          return (
            <Box
              key={slot.id}
              pos="absolute"
              draggable
              onDragStart={(e: React.DragEvent) => dragStart(e, { kind: 'pitch', id: p.player_id })}
              onDragEnd={finish}
              onDragOver={(e: React.DragEvent) => {
                if (!droppable(p)) return
                e.preventDefault()
                setOver(`p${p.player_id}`)
              }}
              onDragLeave={() => setOver((o) => (o === `p${p.player_id}` ? null : o))}
              onDrop={(e: React.DragEvent) => {
                e.preventDefault()
                dropOnPlayer(p)
              }}
              onClick={() => onInspect(p.index)}
              title={`${p.name} · ${p.position} · OVR ${p.ovr} · match rating ${p.rating.toFixed(1)} · energy ${p.energy}%${leaving.has(p.player_id) ? ' · going off at the next stoppage' : ''}`}
              style={{ left, top, transform: 'translate(-50%, -50%)', width: 66, textAlign: 'center', cursor: 'grab' }}
            >
              <Box
                mx="auto"
                w={32}
                h={32}
                style={{
                  borderRadius: '50%',
                  background: '#1c7ed6',
                  border: `3px solid ${energyColor(p.energy)}`,
                  boxShadow: `0 0 0 2px ${ring}`,
                  color: 'white',
                  fontWeight: 700,
                  fontSize: 12,
                  lineHeight: '26px',
                }}
              >
                {p.number}
              </Box>
              <Text c="white" fw={600} truncate style={{ fontSize: 11, textShadow: '0 1px 2px black' }}>
                {p.short_name}
              </Text>
              <Text fw={700} c={matchRatingColor(p.rating)} style={{ background: 'rgba(0,0,0,0.55)', borderRadius: 4, fontSize: 10, whiteSpace: 'nowrap' }}>
                {p.position} {p.rating.toFixed(1)}
              </Text>
            </Box>
          )
        })}
      </Box>
      <Text size="xs" c="dimmed" mt={4}>
        Drag a substitute onto a player to bring him on, or one player onto another to swap their positions. The ring
        shows energy; click a player for his card.
      </Text>
      <Text size="xs" fw={600} mt={6} mb={2}>
        Bench {canSub ? '' : '(no substitutions left)'}
      </Text>
      <Group gap={6}>
        {bench.map((b) => {
          const target = over === `b${b.player_id}` && drag?.kind === 'pitch' && canSub
          return (
            <Badge
              key={b.player_id}
              size="lg"
              radius="sm"
              variant={coming.has(b.player_id) ? 'filled' : 'light'}
              color={coming.has(b.player_id) ? 'orange' : 'teal'}
              draggable={canSub && !coming.has(b.player_id)}
              onDragStart={(e: React.DragEvent) => dragStart(e, { kind: 'bench', id: b.player_id })}
              onDragEnd={finish}
              onDragOver={(e: React.DragEvent) => {
                if (drag?.kind !== 'pitch' || !canSub) return
                e.preventDefault()
                setOver(`b${b.player_id}`)
              }}
              onDragLeave={() => setOver((o) => (o === `b${b.player_id}` ? null : o))}
              onDrop={(e: React.DragEvent) => {
                e.preventDefault()
                dropOnBench(b)
              }}
              title={`${b.name} · ${b.positions.join(', ') || b.position} · OVR ${b.ovr} · condition ${b.condition}%`}
              style={{ cursor: canSub ? 'grab' : 'default', textTransform: 'none', outline: target ? '2px solid #ffd43b' : undefined }}
            >
              {b.number} {b.short_name} · {b.position} {b.ovr}
            </Badge>
          )
        })}
      </Group>
    </Box>
  )
}
