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
    <Stack gap={8}>
      {Object.entries(LABELS).map(([key, label]) => {
        const [h, a] = stats[key] ?? [0, 0]
        const total = h + a || 1
        return (
          <div key={key}>
            <Group justify="space-between" mb={2}>
              <Text size="sm" fw={h >= a ? 800 : 500} style={{ fontVariantNumeric: 'tabular-nums' }}>
                {h}
              </Text>
              <Text size="xs" c="dimmed" tt="uppercase" fw={600} style={{ letterSpacing: 0.6 }}>
                {label}
              </Text>
              <Text size="sm" fw={a >= h ? 800 : 500} style={{ fontVariantNumeric: 'tabular-nums' }}>
                {a}
              </Text>
            </Group>
            <Progress.Root size={6} radius="xl" style={{ gap: 2 }}>
              <Progress.Section value={(100 * h) / total} color={TEAM_COLORS[0].shirt} />
              <Progress.Section value={(100 * a) / total} color={TEAM_COLORS[1].shirt} />
            </Progress.Root>
          </div>
        )
      })}
    </Stack>
  )
}
