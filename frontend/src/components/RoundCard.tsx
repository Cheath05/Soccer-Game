import { Badge, Card, Group, Table, Text, Title } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'

import type { CupRound, CupTie, Fixture } from '../api/types'
import { longDate, score } from '../lib/format'
import ClubLink from './ClubLink'

/** A leg seen from the other side: a second leg is played at the tie's away club's ground, so
 * its score and aggregate are turned to read in the tie's order, home club first. */
function turned(f: Fixture): Fixture {
  return { ...f, home_goals: f.away_goals, away_goals: f.home_goals, home_pens: f.away_pens, away_pens: f.home_pens, agg_home: f.agg_away, agg_away: f.agg_home }
}

/** A knockout round's ties and results: a cup's, a European competition's, or a league's play-off
 * (``series``: a best-of round, whose games are each tie's fixtures). */
export default function RoundCard({ round, userId, series }: { round: CupRound; userId: number | undefined; series?: number }) {
  const navigate = useNavigate()
  const ties = round.ties.filter((t) => t.away)
  const exempt = round.ties.filter((t) => !t.away)
  return (
    <Card withBorder padding="sm" aria-label={round.name}>
      <Group justify="space-between" mb={4}>
        <Title order={4}>{round.name}</Title>
        <Text size="sm" c="dimmed">
          {round.dates.map(longDate).join(' and ')}
          {round.legs === 2 ? ' · two legs' : ''}
          {series ? ` · best of ${series}` : ''}
        </Text>
      </Group>
      <Table.ScrollContainer minWidth={520}>
        <Table highlightOnHover>
          <Table.Tbody>
            {ties.map((t) => {
              const mine = userId !== undefined && (t.home.id === userId || t.away?.id === userId)
              const played = t.fixtures.filter((f) => f.status === 'played')
              return (
                <Table.Tr
                  key={t.tie}
                  fw={mine ? 700 : undefined}
                  bg={mine ? 'var(--mantine-primary-color-light)' : undefined}
                  style={{ cursor: played.length ? 'pointer' : undefined }}
                  onClick={() => played.length && void navigate({ to: '/match/$fixtureId', params: { fixtureId: String(played[played.length - 1]!.id) } })}
                >
                  <Table.Td ta="right" w="40%">
                    <Side tie={t} side="home" />
                  </Table.Td>
                  <Table.Td ta="center" style={{ whiteSpace: 'nowrap' }}>
                    {played.length === 0 ? 'v' : t.fixtures.map((f) => (f.status === 'played' ? score(f.home.id === t.home.id ? f : turned(f)) : 'v')).join(' · ')}
                  </Table.Td>
                  <Table.Td w="40%">
                    <Side tie={t} side="away" />
                  </Table.Td>
                </Table.Tr>
              )
            })}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {exempt.length > 0 && (
        <Text size="xs" c="dimmed" mt={4}>
          Exempt (no non-league clubs in the game yet): {exempt.map((t) => t.home.name).join(', ')}
        </Text>
      )}
    </Card>
  )
}

function Side({ tie, side }: { tie: CupTie; side: 'home' | 'away' }) {
  const club = side === 'home' ? tie.home : tie.away
  if (!club) return null
  const won = tie.winner?.id === club.id
  const lost = tie.winner !== null && !won
  return (
    <Group gap={6} wrap="nowrap" justify={side === 'home' ? 'flex-end' : 'flex-start'}>
      {side === 'away' && won && (
        <Badge size="xs" color="teal" variant="light">
          Through
        </Badge>
      )}
      <Text size="sm" fw={won ? 700 : undefined} c={lost ? 'dimmed' : undefined} component="span">
        <ClubLink club={club} />
      </Text>
      {side === 'home' && won && (
        <Badge size="xs" color="teal" variant="light">
          Through
        </Badge>
      )}
    </Group>
  )
}

