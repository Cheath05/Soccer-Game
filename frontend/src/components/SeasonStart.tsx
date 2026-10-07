import { Group, Text, Tooltip } from '@mantine/core'

import { ratingColor } from '../lib/format'

/** A player's change in overall since the season began: "+3" with a green up arrow, "−2" with a
 * red down arrow, or nothing when level. Shared by the squad table and the player page. */
export function SeasonChange({ start, now }: { start: number; now: number }) {
  const change = now - start
  if (change === 0) return null
  const label = change > 0 ? 'Improved since the season began' : 'Declined since the season began'
  return (
    <Tooltip label={label} withArrow>
      <Text span size="sm" fw={600} c={change > 0 ? 'green.7' : 'red.7'} aria-label={label}>
        {change > 0 ? `▲ +${change}` : `▼ −${-change}`}
      </Text>
    </Tooltip>
  )
}

/** A player's overall as the season began, with how it has changed since. Players with no
 * record from the start of the season (youth who joined part-way) show "new". */
export default function SeasonStart({ start, now }: { start: number | null | undefined; now: number }) {
  if (start === null || start === undefined) {
    return (
      <Text size="xs" c="dimmed" span>
        new
      </Text>
    )
  }
  return (
    <Group gap={6} wrap="nowrap" justify="flex-end" component="span" display="inline-flex">
      <Text size="sm" c={ratingColor(start)} fw={700} span>
        {start}
      </Text>
      <SeasonChange start={start} now={now} />
    </Group>
  )
}
