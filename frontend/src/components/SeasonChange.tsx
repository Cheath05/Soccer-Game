import { Text, Tooltip } from '@mantine/core'

/** A player's change in overall since the season began: "▲+3" in green, "▼−2" in red, or
 * nothing when level. Shown beside his overall in the squad and on the player page. */
export function SeasonChange({ start, now }: { start: number | null | undefined; now: number }) {
  if (start === null || start === undefined) return null
  const change = now - start
  if (change === 0) return null
  const label = change > 0 ? `Up ${change} since the season began (was ${start})` : `Down ${-change} since the season began (was ${start})`
  return (
    <Tooltip label={label} withArrow>
      <Text span size="sm" fw={600} c={change > 0 ? 'green.7' : 'red.7'} aria-label={label} style={{ whiteSpace: 'nowrap' }}>
        {change > 0 ? `▲+${change}` : `▼−${-change}`}
      </Text>
    </Tooltip>
  )
}
