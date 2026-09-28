import { Group, Progress, Stack, Text } from '@mantine/core'

import type { TeamStats } from '../api/types'

const ROWS: { key: string; label: string; digits?: number }[] = [
  { key: 'possession', label: 'Possession %' },
  { key: 'shots', label: 'Shots' },
  { key: 'shots_on_target', label: 'On target' },
  { key: 'xg', label: 'Expected goals', digits: 2 },
  { key: 'passes', label: 'Passes' },
  { key: 'passes_completed', label: 'Passes completed' },
  { key: 'corners', label: 'Corners' },
  { key: 'fouls', label: 'Fouls' },
  { key: 'offsides', label: 'Offsides' },
  { key: 'yellow', label: 'Yellow cards' },
  { key: 'red', label: 'Red cards' },
]

export default function MatchStats({ home, away }: { home: TeamStats; away: TeamStats }) {
  return (
    <Stack gap={8}>
      {ROWS.filter((r) => r.key in home).map((r) => {
        const h = home[r.key] ?? 0
        const a = away[r.key] ?? 0
        const total = h + a || 1
        return (
          <div key={r.key}>
            <Group justify="space-between">
              <Text size="sm" fw={600}>
                {h.toFixed(r.digits ?? 0)}
              </Text>
              <Text size="xs" c="dimmed">
                {r.label}
              </Text>
              <Text size="sm" fw={600}>
                {a.toFixed(r.digits ?? 0)}
              </Text>
            </Group>
            <Progress.Root size="sm">
              <Progress.Section value={(100 * h) / total} color="blue" />
              <Progress.Section value={(100 * a) / total} color="red" />
            </Progress.Root>
          </div>
        )
      })}
    </Stack>
  )
}
