import { Box, Paper, Text, Title, Transition } from '@mantine/core'

import { TEAM_COLORS } from './draw'
import type { GoalInfo } from './protocol'
import type { LiveMatch } from './useLiveMatch'

// Shown over the pitch while the picture holds on a goal (a few seconds at any speed): who
// scored, who made it, and the new score.
export default function GoalBanner({ match }: { match: LiveMatch }) {
  const live = match.live
  const playhead = match.playhead.current
  // Up once the picture has reached the goal itself.
  const holding = live?.holding ?? null
  const goal: GoalInfo | null = holding && (playhead === null || playhead >= holding.t - 0.3) ? holding : null
  return (
    <Transition mounted={goal !== null} transition="pop" duration={180} timingFunction="ease-out">
      {(style) =>
        goal && live ? (
          <Box
            pos="absolute"
            top={0}
            left={0}
            right={0}
            bottom={0}
            style={{ ...style, display: 'flex', alignItems: 'center', justifyContent: 'center', pointerEvents: 'none' }}
          >
            <Paper
              role="status"
              aria-label="Goal"
              shadow="xl"
              px="xl"
              py="md"
              style={{
                background: 'rgba(15, 20, 25, 0.86)',
                borderTop: `6px solid ${TEAM_COLORS[goal.team].shirt}`,
                textAlign: 'center',
                minWidth: 280,
              }}
            >
              <Title order={1} c="white" style={{ letterSpacing: 4 }}>
                GOAL!
              </Title>
              <Text size="xl" fw={700} c="white">
                {goal.own_goal ? `Own goal: ${goal.scorer ?? '?'}` : (goal.scorer ?? '?')}
                {goal.penalty ? ' (penalty)' : ''}
              </Text>
              {goal.assist && (
                <Text size="md" c="gray.3">
                  Assist: {goal.assist}
                </Text>
              )}
              <Text size="sm" c="gray.4" mt={6}>
                {live.teams[goal.team].name}
                {goal.clock ? ` · ${goal.clock}` : ''} · {live.teams[0].name} {goal.score[0]}–{goal.score[1]}{' '}
                {live.teams[1].name}
              </Text>
            </Paper>
          </Box>
        ) : (
          <></>
        )
      }
    </Transition>
  )
}
