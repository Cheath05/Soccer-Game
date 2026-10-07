import { Box, Text } from '@mantine/core'

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

interface Props {
  match: LiveMatch
  competition?: string | null // e.g. "Premier League", shown above the score
  unseenGoalT?: number | null // a goal the picture has not shown in the net yet: not counted
}

function Team({ name, color, side }: { name: string; color: string; side: 'home' | 'away' }) {
  const bar = <Box w={5} h={30} style={{ background: color, borderRadius: 3, flex: 'none' }} />
  return (
    <Box style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, justifyContent: side === 'home' ? 'flex-end' : 'flex-start' }}>
      {side === 'away' && bar}
      <Text fw={700} c="white" lineClamp={1} ta={side === 'home' ? 'right' : 'left'} style={{ fontSize: 'clamp(0.95rem, 2.6vw, 1.3rem)', letterSpacing: 0.2 }}>
        {name}
      </Text>
      {side === 'home' && bar}
    </Box>
  )
}

// Score and football clock. The clock follows the pitch picture (which runs a moment behind
// the engine) so a goal and its minute appear together.
export default function ScoreBar({ match, competition, unseenGoalT = null }: Props) {
  const live = match.live
  if (!live) return null
  const playhead = match.playhead.current
  const behind = playhead !== null ? Math.max(0, live.t - playhead) : 0
  // The score follows the picture too: a goal counts once it has been seen in the net.
  const score: [number, number] = [live.score[0], live.score[1]]
  if (playhead !== null && !live.finished) {
    for (const f of live.feed) {
      if (f.type !== 'goal' || f.team === null) continue
      if (f.t > playhead + 0.05 || (unseenGoalT !== null && Math.abs(f.t - unseenGoalT) < 0.01)) score[f.team] -= 1
    }
  }
  const still = live.atBreak || live.finished || live.clock.state !== 'playing'
  const elapsed = still ? live.clock.elapsed : Math.max(0, live.clock.elapsed - behind)
  const clock = live.finished ? 'FT' : live.atBreak ? 'HT' : formatClock(live.clock.period, elapsed)
  const running = !live.paused && !live.atBreak && !live.finished
  const status =
    live.restart && !live.atBreak && !live.finished
      ? `${RESTART_NAMES[live.restart.variant] ?? live.restart.kind} · ${live.teams[live.restart.team].name}`
      : periodName(live.clock.period, live.atBreak, live.finished)
  return (
    <Box
      style={{
        background: 'linear-gradient(135deg, #0e1a2b 0%, #16263d 55%, #12202f 100%)',
        borderRadius: 14,
        padding: '10px 18px 12px',
        boxShadow: '0 1px 2px rgba(0,0,0,0.2), 0 6px 18px rgba(10,20,35,0.22)',
      }}
    >
      {competition && (
        <Text ta="center" size="xs" fw={600} tt="uppercase" mb={4} style={{ color: 'rgba(255,255,255,0.55)', letterSpacing: 1.2 }}>
          {competition}
        </Text>
      )}
      <Box style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) auto minmax(0,1fr)', alignItems: 'center', columnGap: 14 }}>
        <Team name={live.teams[0].name} color={TEAM_COLORS[0].shirt} side="home" />
        <Box style={{ textAlign: 'center' }}>
          <Text
            c="white"
            fw={800}
            aria-label="Score"
            style={{ fontSize: 'clamp(1.7rem, 6vw, 2.6rem)', lineHeight: 1.05, fontVariantNumeric: 'tabular-nums', letterSpacing: 1 }}
          >
            {score[0]} – {score[1]}
          </Text>
          <Box style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
            <Box
              aria-label="Match clock"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                background: 'rgba(255,255,255,0.12)',
                color: '#fff',
                borderRadius: 999,
                padding: '2px 10px',
                fontSize: 13,
                fontWeight: 700,
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {running && <Box w={7} h={7} style={{ background: '#ef4444', borderRadius: '50%' }} />}
              {clock}
            </Box>
            {live.clock.added !== null && !live.finished && !live.atBreak && (
              <Box style={{ background: 'rgba(251,146,60,0.25)', color: '#fdba74', borderRadius: 999, padding: '2px 8px', fontSize: 12, fontWeight: 700 }}>
                +{live.clock.added}
              </Box>
            )}
          </Box>
        </Box>
        <Team name={live.teams[1].name} color={TEAM_COLORS[1].shirt} side="away" />
      </Box>
      <Text ta="center" size="xs" mt={4} style={{ color: 'rgba(255,255,255,0.6)' }}>
        {status}
      </Text>
    </Box>
  )
}
