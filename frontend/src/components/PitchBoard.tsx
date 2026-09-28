import { Box, Text } from '@mantine/core'

import type { Formation, SheetEntry } from '../api/types'
import { ratingColor } from '../lib/format'

const W = 340
const H = 480

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
        // Formations span roughly x = 0.04 (keeper) to 0.72 (strikers); stretch that range
        // over the board so the lines don't bunch up.
        const left = slot.y * (W - 60) + 30
        const top = 34 + (1 - (slot.x - 0.02) / 0.76) * (H - 80)
        const active = selected === slot.id
        return (
          <Box
            key={slot.id}
            onClick={() => onSelect(slot.id)}
            pos="absolute"
            style={{ left, top, transform: 'translate(-50%, -50%)', cursor: 'pointer', textAlign: 'center', width: 84 }}
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
            <Text size="xs" c="white" fw={600} truncate style={{ textShadow: '0 1px 2px black' }}>
              {entry?.name.split(' ').slice(-1)[0] ?? slot.position}
            </Text>
            {entry && (
              <Text size="xs" fw={700} c={ratingColor(entry.rating)} style={{ background: 'rgba(0,0,0,0.55)', borderRadius: 4 }}>
                {slot.position} {entry.rating}
              </Text>
            )}
          </Box>
        )
      })}
    </Box>
  )
}
