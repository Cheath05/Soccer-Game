import { Box, Text } from '@mantine/core'
import { useState } from 'react'

import type { Formation, SheetEntry } from '../api/types'
import { ratingColor } from '../lib/format'
import { breakdownText, fitColor } from '../lib/slotRating'

const W = 340
const H = 480
const LABEL_MAX = 84 // widest a player's label may be
const LABEL_MIN = 44 // narrowest: where players stand this close, long names are cut short
const LABEL_HEIGHT = 74 // the disc, name and rating together: labels this far apart vertically can't clash
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
  picked,
  dragging,
  onDragPlayer,
  onDropOnSlot,
}: {
  formation: Formation
  starters: SheetEntry[]
  selected: string | null
  onSelect: (slot: string) => void
  /** Click-to-move: the player waiting for a new place, highlighted on the board. */
  picked?: number | null
  /** Drag and drop (the tactics screen): the player being dragged, and what to do on a drop. */
  dragging?: number | null
  onDragPlayer?: (playerId: number | null) => void
  onDropOnSlot?: (slot: string) => void
}) {
  const [over, setOver] = useState<string | null>(null)
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
        const isPicked = picked != null && picked === entry?.player_id
        const warn = entry ? fitColor(entry) : null
        const target = over === slot.id && dragging != null && dragging !== entry?.player_id
        return (
          <Box
            key={slot.id}
            onClick={() => onSelect(slot.id)}
            draggable={!!entry && !!onDragPlayer}
            onDragStart={(e: React.DragEvent) => {
              if (!entry) return
              e.dataTransfer.effectAllowed = 'move'
              e.dataTransfer.setData('text/plain', String(entry.player_id))
              onDragPlayer?.(entry.player_id)
            }}
            onDragEnd={() => {
              setOver(null)
              onDragPlayer?.(null)
            }}
            onDragOver={(e: React.DragEvent) => {
              if (dragging == null) return
              e.preventDefault()
              setOver(slot.id)
            }}
            onDragLeave={() => setOver((o) => (o === slot.id ? null : o))}
            onDrop={(e: React.DragEvent) => {
              e.preventDefault()
              setOver(null)
              if (dragging != null) onDropOnSlot?.(slot.id)
            }}
            pos="absolute"
            title={entry ? breakdownText(entry) : undefined}
            style={{ left, top, transform: 'translate(-50%, -50%)', cursor: onDragPlayer && picked == null ? 'grab' : 'pointer', textAlign: 'center', width }}
          >
            <Box
              mx="auto"
              w={34}
              h={34}
              style={{
                borderRadius: '50%',
                background: isPicked ? '#fab005' : active ? '#f59f00' : '#1c7ed6',
                border: `2px solid ${target ? '#ffd43b' : 'white'}`,
                boxShadow: isPicked ? '0 0 0 4px rgba(255,212,59,0.9)' : target ? '0 0 0 4px rgba(255,212,59,0.7)' : warn ? `0 0 0 3px ${warn === 'red' ? '#fa5252' : '#fd7e14'}` : undefined,
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
            {entry && entry.overall !== entry.rating && (
              <Text size="xs" style={{ fontSize: 10, whiteSpace: 'nowrap', overflow: 'hidden', textShadow: '0 1px 2px black' }} c={warn === 'red' ? 'red.3' : warn ? 'orange.3' : 'gray.3'}>
                OVR {entry.overall}
                {warn ? ' !' : ''}
              </Text>
            )}
          </Box>
        )
      })}
    </Box>
  )
}
