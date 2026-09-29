import { Badge, Box, Card, Group, Stack, Text, Title } from '@mantine/core'

import { formatClock, periodName } from './clock'
import { TEAM_COLORS } from './draw'
import type { LiveMatch } from './useLiveMatch'

const RESTART_NAMES: Record<string, string> = {
  throw_in: 'Throw-in',
  long_throw: 'Long throw',
  goal_kick: 'Goal kick',
  corner: 'Corner',
  free_kick: 'Free kick',
  dangerous_free_kick: 'Free kick in range',
  quick_free_kick: 'Quick free kick',
  offside: 'Offside',
  penalty: 'Penalty',
  kickoff: 'Kick-off',
  kickoff_after_goal: 'Kick-off',
}

// Score and football clock. The clock follows the pitch picture (which runs a moment behind
// the engine) so a goal and its minute appear together.
export default function ScoreBar({ match }: { match: LiveMatch }) {
  const live = match.live
  if (!live) return null
  const behind = match.playhead.current !== null ? Math.max(0, live.t - match.playhead.current) : 0
  const still = live.atBreak || live.finished || live.clock.state !== 'playing'
  const elapsed = still ? live.clock.elapsed : Math.max(0, live.clock.elapsed - behind)
  const clock = live.finished ? 'FT' : live.atBreak ? 'HT' : formatClock(live.clock.period, elapsed)
  return (
    <Card withBorder padding="xs">
      <Group justify="space-between" wrap="nowrap">
        <Group gap="xs" wrap="nowrap" style={{ flex: 1 }}>
          <Box w={14} h={14} style={{ background: TEAM_COLORS[0].shirt, borderRadius: 3 }} />
          <Title order={4} lineClamp={1}>
            {live.teams[0].name}
          </Title>
        </Group>
        <Stack gap={2} align="center">
          <Title order={2} style={{ fontVariantNumeric: 'tabular-nums' }}>
            {live.score[0]} – {live.score[1]}
          </Title>
          <Group gap={6}>
            <Badge variant="filled" color="dark" size="lg" aria-label="Match clock" style={{ fontVariantNumeric: 'tabular-nums' }}>
              {clock}
            </Badge>
            {live.clock.added !== null && !live.finished && !live.atBreak && (
              <Badge variant="light" color="orange" size="lg">
                +{live.clock.added}
              </Badge>
            )}
          </Group>
          <Text size="xs" c="dimmed">
            {live.restart && !live.atBreak && !live.finished
              ? `${RESTART_NAMES[live.restart.variant] ?? live.restart.kind} – ${live.teams[live.restart.team].name}`
              : periodName(live.clock.period, live.atBreak, live.finished)}
          </Text>
        </Stack>
        <Group gap="xs" wrap="nowrap" justify="flex-end" style={{ flex: 1 }}>
          <Title order={4} lineClamp={1}>
            {live.teams[1].name}
          </Title>
          <Box w={14} h={14} style={{ background: TEAM_COLORS[1].shirt, borderRadius: 3 }} />
        </Group>
      </Group>
    </Card>
  )
}
