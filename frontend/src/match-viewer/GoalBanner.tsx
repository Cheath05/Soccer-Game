import { Box, Text, Transition } from '@mantine/core'

import { TEAM_COLORS } from './draw'
import type { GoalInfo } from './protocol'
import type { LiveState } from './protocol'

// Shown over the top of the pitch once the ball is in the net (PitchView says when, from the
// same clock that draws the ball) and until play moves on: who scored, who made it, and the
// new score.
export default function GoalBanner({ goal, live }: { goal: GoalInfo | null; live: LiveState | null }) {
  // Keep the last goal while the card fades out.
  return (
    <Transition mounted={goal !== null} transition="slide-down" duration={220} timingFunction="ease-out">
      {(style) =>
        goal && live ? (
          <Box
            pos="absolute"
            top={0}
            left={0}
            right={0}
            style={{ ...style, display: 'flex', justifyContent: 'center', padding: '5% 12px 0', pointerEvents: 'none' }}
          >
            <Box
              role="status"
              aria-label="Goal"
              style={{
                background: 'rgba(11, 18, 30, 0.84)',
                backdropFilter: 'blur(10px)',
                borderRadius: 16,
                borderLeft: `6px solid ${TEAM_COLORS[goal.team].shirt}`,
                boxShadow: '0 10px 32px rgba(0,0,0,0.38)',
                padding: '12px 24px 12px 20px',
                textAlign: 'left',
                minWidth: 260,
                maxWidth: '94%',
                color: '#fff',
              }}
            >
              <Text fw={800} style={{ letterSpacing: 5, fontSize: 'clamp(1.4rem, 4.5vw, 2rem)', lineHeight: 1.1, color: '#fde047' }}>
                GOAL!
              </Text>
              <Text fw={700} style={{ fontSize: 'clamp(1rem, 3vw, 1.3rem)' }}>
                {goal.own_goal ? `Own goal: ${goal.scorer ?? '?'}` : (goal.scorer ?? '?')}
                {goal.penalty ? ' (penalty)' : ''}
              </Text>
              {goal.assist && (
                <Text size="sm" style={{ color: 'rgba(255,255,255,0.7)' }}>
                  Assist: {goal.assist}
                </Text>
              )}
              <Text size="sm" mt={6} style={{ color: 'rgba(255,255,255,0.65)', fontVariantNumeric: 'tabular-nums' }}>
                {live.teams[goal.team].name}
                {goal.clock ? ` · ${goal.clock}` : ''} · {live.teams[0].name} {goal.score[0]}–{goal.score[1]} {live.teams[1].name}
              </Text>
            </Box>
          </Box>
        ) : (
          <></>
        )
      }
    </Transition>
  )
}
