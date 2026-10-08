import { Group, Text } from '@mantine/core'

import type { SheetEntry } from '../api/types'
import { fitColor, signed } from '../lib/slotRating'

/** The same as a line of text with the reasons coloured: amber when a little off, red out of position. */
export function SlotBreakdown({ entry }: { entry: SheetEntry }) {
  const color = fitColor(entry)
  return (
    <Group gap={6} wrap="wrap" component="span" style={{ rowGap: 0 }}>
      <Text span size="xs" c="dimmed">
        OVR {entry.overall} ({entry.best_position})
      </Text>
      {entry.adjustments.map((a) => (
        <Text
          key={a.kind}
          span
          size="xs"
          fw={600}
          c={a.kind === 'position' ? (color ?? 'orange') : a.kind === 'condition' ? 'yellow.8' : 'dimmed'}
        >
          {a.label} {signed(a.delta)}
        </Text>
      ))}
    </Group>
  )
}
