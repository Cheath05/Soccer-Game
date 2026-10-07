import { Box, Text } from '@mantine/core'

import type { Formation, SheetEntry } from '../api/types'
import { ratingColor } from '../lib/format'

const W = 340
const H = 480
const LABEL_MAX = 84 // widest a player's label may be
const LABEL_MIN = 44 // narrowest: where players stand this close, long names are cut short
const LABEL_HEIGHT = 62 // the disc, name and rating together: labels this far apart vertically can't clash
const LABEL_GAP = 4

/** Where a slot's disc sits on the board. Formations span roughly x = 0.04 (keeper) to 0.72
 * (strikers); that range is stretched over the board so the lines don't bunch up. */
function place(slot: { x: number; y: number }) {
  return { left: slot.y * (W - 60) + 30, top: 34 + (1 - (slot.x - 0.02) / 0.76) * (H - 80) }
}

/** Vertical tactics board: own goal at the bottom. Slot coordinates come from the formation data. */
export default function PitchBoard({
  formation,
  starters,
  selected,
  onSelect,
}: {
  formation: Formation
  starters: SheetEntry[]
  selected: string | null
  onSelect: (slot: string) => void
}) {
  const bySlot = new Map(starters.map((s) => [s.slot, s]))
  // A label is as wide as the room beside it: no wider than the gap to the nearest player it
  // could overlap, so two centre-backs or a front pair never clash, whatever the formation.
  const spots = formation.slots.map((slot) => ({ id: slot.id, ...place(slot) }))
  const labelWidth = (id: string) => {
    const me = spots.find((s) => s.id === id)
    if (!me) return LABEL_MAX
    const gaps = spots
      .filter((o) => o.id !== id && Math.abs(o.top - me.top) < LABEL_HEIGHT)
      .map((o) => Math.abs(o.left - me.left) - LABEL_GAP)
    return Math.max(LABEL_MIN, Math.min(LABEL_MAX, ...gaps))
  }
  return (
    <Box pos="relative" w={W} h={H} style={{ borderRadius: 8, overflow: 'hidden', flexShrink: 0 }}>
      <svg width={W} height={H} style={{ position: 'absolute', inset: 0 }}>
        <rect width={W} height={H} fill="#2f7d3b" />
        {Array.from({ length: 8 }, (_, i) => (
          <rect key={i} y={(i * H) / 8} width={W} height={H / 16} fill="#2c7437" />
        ))}
        <g stroke="rgba(255,255,255,0.7)" strokeWidth={2} fill="none">
          <rect x={6} y={6} width={W - 12} height={H - 12} />
          <line x1={6} y1={H / 2} x2={W - 6} y2={H / 2} />
          <circle cx={W / 2} cy={H / 2} r={40} />
          <rect x={W * 0.2} y={6} width={W * 0.6} height={H * 0.16} />
          <rect x={W * 0.2} y={H - 6 - H * 0.16} width={W * 0.6} height={H * 0.16} />
        </g>
      </svg>
      {formation.slots.map((slot) => {
        const entry = bySlot.get(slot.id)
        const { left, top } = place(slot)
        const width = labelWidth(slot.id)
        const surname = entry?.name.split(' ').slice(-1)[0]
        const active = selected === slot.id
        return (
          <Box
            key={slot.id}
            onClick={() => onSelect(slot.id)}
            pos="absolute"
            style={{ left, top, transform: 'translate(-50%, -50%)', cursor: 'pointer', textAlign: 'center', width }}
          >
            <Box
              mx="auto"
              w={34}
              h={34}
              style={{
                borderRadius: '50%',
                background: active ? '#f59f00' : '#1c7ed6',
                border: '2px solid white',
                color: 'white',
                fontWeight: 700,
                fontSize: 13,
                lineHeight: '30px',
              }}
            >
              {entry?.number ?? ''}
            </Box>
            <Text size="xs" c="white" fw={600} truncate title={entry?.name} style={{ textShadow: '0 1px 2px black', fontSize: 11 }}>
              {surname ?? slot.position}
            </Text>
            {entry && (
              <Text size="xs" fw={700} c={ratingColor(entry.rating)} style={{ background: 'rgba(0,0,0,0.55)', borderRadius: 4, fontSize: 11, whiteSpace: 'nowrap', overflow: 'hidden' }}>
                {slot.position} {entry.rating}
              </Text>
            )}
          </Box>
        )
      })}
    </Box>
  )
}
