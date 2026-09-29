import { Group, Progress, Stack, Text } from '@mantine/core'

import { TEAM_COLORS } from './draw'

const LABELS: Record<string, string> = {
  possession: 'Possession %',
  shots: 'Shots',
  on_target: 'On target',
  xg: 'Expected goals',
  passes: 'Passes',
  pass_pct: 'Pass accuracy %',
  corners: 'Corners',
  fouls: 'Fouls',
}

export default function StatsPanel({ stats }: { stats: Record<string, number[]> }) {
  return (
    <Stack gap={6}>
      {Object.entries(LABELS).map(([key, label]) => {
        const [h, a] = stats[key] ?? [0, 0]
        const total = h + a || 1
        return (
          <div key={key}>
            <Group justify="space-between">
              <Text size="sm" fw={600}>
                {h}
              </Text>
              <Text size="xs" c="dimmed">
                {label}
              </Text>
              <Text size="sm" fw={600}>
                {a}
              </Text>
            </Group>
            <Progress.Root size="sm">
              <Progress.Section value={(100 * h) / total} color={TEAM_COLORS[0].shirt} />
              <Progress.Section value={(100 * a) / total} color={TEAM_COLORS[1].shirt} />
            </Progress.Root>
          </div>
        )
      })}
    </Stack>
  )
}
