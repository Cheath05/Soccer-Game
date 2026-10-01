import { Badge, Card, Group, Table, Text, Title } from '@mantine/core'

import { useClubHistory } from '../api/hooks'
import { OUTCOMES, ordinal } from '../lib/format'

/** Where a club finished in each season of the career so far, and this season's position. */
export default function ClubHistoryCard({ clubId }: { clubId: number }) {
  const history = useClubHistory(clubId).data
  if (!history) return null
  const honours = [
    history.titles && `${history.titles} ${history.titles === 1 ? 'title' : 'titles'}`,
    history.promotions && `${history.promotions} ${history.promotions === 1 ? 'promotion' : 'promotions'}`,
    history.relegations && `${history.relegations} ${history.relegations === 1 ? 'relegation' : 'relegations'}`,
  ].filter(Boolean)
  return (
    <Card withBorder padding="sm" aria-label="Club history">
      <Group justify="space-between" mb={4}>
        <Title order={4}>History</Title>
        <Text size="sm" c="dimmed">
          {honours.length ? honours.join(' · ') : 'No honours yet in this career'}
        </Text>
      </Group>
      <Table.ScrollContainer minWidth={760}>
        <Table striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Season</Table.Th>
              <Table.Th>League</Table.Th>
              <Table.Th ta="right">Pos</Table.Th>
              <Table.Th ta="right">P</Table.Th>
              <Table.Th ta="right">W</Table.Th>
              <Table.Th ta="right">D</Table.Th>
              <Table.Th ta="right">L</Table.Th>
              <Table.Th ta="right">GD</Table.Th>
              <Table.Th ta="right">Pts</Table.Th>
              <Table.Th />
              <Table.Th>Cups</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {history.seasons.map((s) => {
              const gd = s.goals_for - s.goals_against
              const outcome = s.outcome ? OUTCOMES[s.outcome] : undefined
              return (
                <Table.Tr key={s.season_id}>
                  <Table.Td>{s.season}</Table.Td>
                  <Table.Td>{s.competition.name}</Table.Td>
                  <Table.Td ta="right" fw={700}>
                    {s.position ? ordinal(s.position) : '–'}
                  </Table.Td>
                  <Table.Td ta="right">{s.played}</Table.Td>
                  <Table.Td ta="right">{s.won}</Table.Td>
                  <Table.Td ta="right">{s.drawn}</Table.Td>
                  <Table.Td ta="right">{s.lost}</Table.Td>
                  <Table.Td ta="right">{gd > 0 ? `+${gd}` : gd}</Table.Td>
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
                  <Table.Td>
                    <Group gap={4} wrap="nowrap">
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
