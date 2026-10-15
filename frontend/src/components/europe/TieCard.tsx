import { Box, Text } from '@mantine/core'

import type { Career, CupTie, Fixture } from '../../api/types'
import ClubLink from '../ClubLink'
import { dayDate } from './shared'
import { FixtureLink } from './Pieces'

const goalsOf = (f: Fixture, clubId: number) => (f.home.id === clubId ? f.home_goals : f.away_goals)

/** One European tie as a small scoreboard: a line per club, a column per leg and, over two legs,
 * the aggregate. The winner is bold, the loser dimmed, your club's tie tinted. A leg's score
 * opens its match report. */
export default function TieCard({ tie, legs, userId, career }: { tie: CupTie; legs: number; userId: number | undefined; career: Career | undefined }) {
  const clubs = tie.away ? [tie.home, tie.away] : [tie.home]
  const mine = userId !== undefined && clubs.some((c) => c.id === userId)
  const played = tie.fixtures.filter((f) => f.status === 'played')
  const next = tie.fixtures.find((f) => f.status !== 'played')
  const columns = `minmax(0, 1fr) repeat(${legs}, 22px)${legs > 1 ? ' 30px' : ''}`
  const decider = [...played].reverse().find((f) => f.home_pens !== null && f.away_pens !== null)
  let note: string | null = null
  if (decider && tie.winner && decider.home_pens !== null && decider.away_pens !== null) {
    const winnerPens = decider.home.id === tie.winner.id ? decider.home_pens : decider.away_pens
    const loserPens = decider.home.id === tie.winner.id ? decider.away_pens : decider.home_pens
    note = `${tie.winner.name} won ${winnerPens}–${loserPens} on penalties`
  } else if (played.some((f) => f.extra_time)) {
    note = 'Decided after extra time'
  }
  return (
    <Box
      p={6}
      aria-label={clubs.map((c) => c.name).join(' v ')}
      style={{
        border: `1px solid ${mine ? 'var(--mantine-primary-color-filled)' : 'var(--mantine-color-default-border)'}`,
        borderRadius: 'var(--mantine-radius-md)',
        background: mine ? 'var(--mantine-primary-color-light)' : 'var(--mantine-color-body)',
      }}
    >
      {clubs.map((club) => {
        const won = tie.winner?.id === club.id
        const lost = tie.winner !== null && !won
        const total = played.reduce((sum, f) => sum + (goalsOf(f, club.id) ?? 0), 0)
        return (
          <div key={club.id} style={{ display: 'grid', gridTemplateColumns: columns, alignItems: 'center', columnGap: 2, minHeight: 24 }}>
            <Text size="sm" truncate title={club.name} fw={won || club.id === userId ? 700 : undefined} c={lost ? 'dimmed' : undefined}>
              <ClubLink club={club} />
            </Text>
            {Array.from({ length: legs }, (_, i) => {
              const leg = tie.fixtures[i]
              const goals = leg && leg.status === 'played' ? goalsOf(leg, club.id) : null
              return (
                <Text key={i} size="sm" ta="center" c={goals === null ? 'dimmed' : lost ? 'dimmed' : undefined} title={leg ? dayDate(leg.date) : undefined}>
                  {leg && goals !== null ? (
                    <FixtureLink fixture={leg} career={career}>
                      {goals}
                    </FixtureLink>
                  ) : (
                    '–'
                  )}
                </Text>
              )
            })}
            {legs > 1 && (
              <Text size="sm" ta="center" fw={700} c={lost ? 'dimmed' : undefined} style={{ borderLeft: '1px solid var(--mantine-color-default-border)' }}>
                {played.length ? total : ''}
              </Text>
            )}
          </div>
        )
      })}
      {(note || (next && !tie.winner)) && (
        <Text size="xs" c="dimmed" mt={2}>
          {note ?? (next ? <FixtureLink fixture={next} career={career}>{`Next: ${dayDate(next.date)}`}</FixtureLink> : null)}
        </Text>
      )}
    </Box>
  )
}
