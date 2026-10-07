import { Group, Text, Tooltip } from '@mantine/core'
import type { MantineSize } from '@mantine/core'

import { ratingColor } from '../lib/format'

/** A player's overall, with a green up or red down arrow while it's been rising or falling
 * over the past few months. Steady players get an empty slot, so the numbers stay aligned.
 * ``hint`` words the arrow's tooltip when it means something else, as in a season's summary. */
export default function Overall({
  value,
  trend,
  size = 'sm',
  hint,
}: {
  value: number
  trend?: number
  size?: MantineSize
  hint?: { up: string; down: string }
}) {
  const label = trend && trend > 0 ? (hint?.up ?? 'Rising lately') : (hint?.down ?? 'Falling lately')
  return (
    <Group gap={2} wrap="nowrap" justify="flex-end" component="span" display="inline-flex">
      <Text fw={700} c={ratingColor(value)} size={size} span>
        {value}
      </Text>
      <Text span size="xs" w={12} ta="center" c={trend && trend > 0 ? 'green.7' : 'red.7'}>
        {trend ? (
          <Tooltip label={label} withArrow>
            <span aria-label={label}>{trend > 0 ? '▲' : '▼'}</span>
          </Tooltip>
        ) : null}
      </Text>
    </Group>
  )
}
