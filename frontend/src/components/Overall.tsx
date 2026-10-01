import { Group, Text, Tooltip } from '@mantine/core'
import type { MantineSize } from '@mantine/core'

import { ratingColor } from '../lib/format'

/** A player's overall, with a green up or red down arrow while it's been rising or falling
 * over the past few months. Steady players get an empty slot, so the numbers stay aligned. */
export default function Overall({ value, trend, size = 'sm' }: { value: number; trend?: number; size?: MantineSize }) {
  const label = trend && trend > 0 ? 'Rising lately' : 'Falling lately'
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
