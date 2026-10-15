import { Badge, Card, Group, Stack, Table, Text, Title } from '@mantine/core'

import { useClubHistory } from '../api/hooks'
import type { Trophy } from '../api/types'
import { useDevice } from '../lib/device'
import { EUROPE_COLOR, competitionColor } from '../lib/competitionColors'
import { OUTCOMES, ordinal } from '../lib/format'
import { EuropeBadge, TrebleBanner } from './EuropeHonours'

/** Where a club finished in each season of the career so far, and this season's position. */
export default function ClubHistoryCard({ clubId }: { clubId: number }) {
  const { phone } = useDevice()
  const history = useClubHistory(clubId).data
  if (!history) return null
  const honours = [
    history.titles && `${history.titles} ${history.titles === 1 ? 'title' : 'titles'}`,
    history.promotions && `${history.promotions} ${history.promotions === 1 ? 'promotion' : 'promotions'}`,
    history.relegations && `${history.relegations} ${history.relegations === 1 ? 'relegation' : 'relegations'}`,
  ].filter(Boolean)
  const trophyColor = (t: Trophy) => (t.kind === 'europe' ? EUROPE_COLOR[t.key] : t.kind === 'league' ? 'yellow' : competitionColor(t.key))
  return (
    <Card withBorder padding="sm" aria-label="Club history">
      <Group justify="space-between" mb={4}>
        <Title order={4}>History</Title>
        <Text size="sm" c="dimmed">
          {honours.length ? honours.join(' · ') : 'No honours yet in this career'}
        </Text>
      </Group>
      {history.trophies.length > 0 && (
        <Stack gap={4} mb="xs" aria-label="Trophies">
          {history.trophies.map((t) => (
            <Group key={`${t.kind}-${t.key}`} gap={8} wrap="nowrap" align="flex-start">
              <Badge size="sm" variant="filled" color={trophyColor(t)} miw={36} style={{ flexShrink: 0 }}>
                ×{t.seasons.length}
              </Badge>
              <Text size="sm">
                {t.name}{' '}
                <Text span c="dimmed" size="sm">
                  ({t.seasons.join(', ')})
                </Text>
              </Text>
            </Group>
          ))}
        </Stack>
      )}
      {history.seasons
        .filter((s) => s.treble)
        .map((s) => (
          <div key={`treble-${s.season_id}`} style={{ marginBottom: 'var(--mantine-spacing-xs)' }}>
            <TrebleBanner
              title={history.club.name + ' win the Treble'}
              season={s.season}
              trophies={s.treble_trophies}
            />
          </div>
        ))}
      <Table.ScrollContainer minWidth={phone ? 0 : 760}>
        <Table striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Season</Table.Th>
              <Table.Th>League</Table.Th>
              <Table.Th ta="right">Pos</Table.Th>
              <Table.Th ta="right" visibleFrom="sm">P</Table.Th>
              <Table.Th ta="right" visibleFrom="sm">W</Table.Th>
              <Table.Th ta="right" visibleFrom="sm">D</Table.Th>
              <Table.Th ta="right" visibleFrom="sm">L</Table.Th>
              <Table.Th ta="right" visibleFrom="sm">GD</Table.Th>
              <Table.Th ta="right">Pts</Table.Th>
              <Table.Th />
              <Table.Th visibleFrom="sm">Europe and cups</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {history.seasons.map((s) => {
              const gd = s.goals_for - s.goals_against
              const outcome = s.outcome ? OUTCOMES[s.outcome] : undefined
              return (
                <Table.Tr key={s.season_id}>
                  <Table.Td>
                    {s.season}
                    {s.treble && (
                      <Badge ml={6} size="xs" variant="gradient" gradient={{ from: 'yellow.4', to: 'yellow.7' }} c="dark.9">
                        Treble
                      </Badge>
                    )}
                    {s.europe.length > 0 && (
                      <Stack gap={2} mt={4} hiddenFrom="sm">
                        {s.europe.map((run) => (
                          <div key={run.key}>
                            <EuropeBadge run={run} />
                          </div>
                        ))}
                      </Stack>
                    )}
                  </Table.Td>
                  <Table.Td>{s.competition.name}</Table.Td>
                  <Table.Td ta="right" fw={700}>
                    {s.position ? ordinal(s.position) : '–'}
                  </Table.Td>
                  <Table.Td ta="right" visibleFrom="sm">{s.played}</Table.Td>
                  <Table.Td ta="right" visibleFrom="sm">{s.won}</Table.Td>
                  <Table.Td ta="right" visibleFrom="sm">{s.drawn}</Table.Td>
                  <Table.Td ta="right" visibleFrom="sm">{s.lost}</Table.Td>
                  <Table.Td ta="right" visibleFrom="sm">{gd > 0 ? `+${gd}` : gd}</Table.Td>
                  <Table.Td ta="right" fw={700}>
                    {s.points}
                  </Table.Td>
                  <Table.Td>
                    {s.final ? (
                      outcome && (
                        <Badge size="sm" variant="light" color={outcome.color}>
                          {outcome.label}
                        </Badge>
                      )
                    ) : (
                      <Badge size="sm" variant="outline" color="gray">
                        In progress
                      </Badge>
                    )}
                  </Table.Td>
                  <Table.Td visibleFrom="sm">
                    <Group gap={4} wrap="nowrap">
                      {s.europe.map((run) => (
                        <EuropeBadge key={run.key} run={run} />
                      ))}
                      {s.cups.map((run) => (
                        <Badge key={run.key} size="sm" variant={run.won ? 'filled' : 'light'} color={run.won ? 'yellow' : run.out ? 'gray' : 'blue'}>
                          {run.name}: {run.reached}
                        </Badge>
                      ))}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              )
            })}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Card>
  )
}
