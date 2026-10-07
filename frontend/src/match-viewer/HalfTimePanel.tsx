import { Button, Group, Paper, SimpleGrid, Stack, Text, Title } from '@mantine/core'

import StatsPanel from './StatsPanel'
import type { LiveMatch } from './useLiveMatch'

// Shown over the pitch at half-time (and the breaks around extra time). Changes made in the
// Tactics and Subs tabs now take effect when the next period starts.
export default function HalfTimePanel({ match }: { match: LiveMatch }) {
  const { live, send } = match
  if (!live) return null
  const next = live.clock.period === 1 ? 'Start second half' : live.clock.period === 2 ? 'Start extra time' : 'Start second half of extra time'
  const mine = live.status.players.filter((p) => p.team === live.userTeam && p.active)
  const tired = [...mine].sort((a, b) => a.energy - b.energy).slice(0, 3)
  const best = [...mine].sort((a, b) => b.rating - a.rating).slice(0, 3)
  return (
    <Paper
      shadow="xl"
      p="md"
      radius="lg"
      withBorder
      w={460}
      maw="94%"
      mah="96%"
      style={{ overflowY: 'auto', backdropFilter: 'blur(12px)', background: 'color-mix(in srgb, var(--mantine-color-body) 90%, transparent)' }}
    >
      <Stack gap="sm">
        <Group justify="space-between">
          <Title order={3}>{live.clock.period === 1 ? 'Half-time' : 'Break'}</Title>
          <Title order={3}>
            {live.score[0]} – {live.score[1]}
          </Title>
        </Group>
        <StatsPanel stats={live.stats} />
        <SimpleGrid cols={2}>
          <Stack gap={2}>
            <Text size="xs" c="dimmed">
              Most tired
            </Text>
            {tired.map((p) => (
              <Text key={p.player_id} size="sm">
                {p.short_name} · {p.energy}%
              </Text>
            ))}
          </Stack>
          <Stack gap={2}>
            <Text size="xs" c="dimmed">
              Best rated
            </Text>
            {best.map((p) => (
              <Text key={p.player_id} size="sm">
                {p.short_name} · {p.rating.toFixed(1)}
              </Text>
            ))}
          </Stack>
        </SimpleGrid>
        <Text size="xs" c="dimmed">
          Make any changes in the Tactics and Subs tabs before the restart.
        </Text>
        <Button color="teal" radius="xl" onClick={() => send({ type: 'start_period' })}>
          {next}
        </Button>
      </Stack>
    </Paper>
  )
}
