import { Card, Loader, Stack, Table, Text, Title } from '@mantine/core'

import { useEuropeRankings } from '../../api/hooks'
import { nationName } from '../../lib/format'
import ClubLink from '../ClubLink'

const num = (x: number) => x.toFixed(3).replace(/0$/, '')

/** UEFA's country ranking (five seasons and their total) and, below it, the club coefficient
 * ranking. Your own country and club are highlighted. */
export default function Rankings({ userId, userNation }: { userId: number | undefined; userNation: string | undefined }) {
  const q = useEuropeRankings()
  const data = q.data
  if (q.isPending) return <Loader size="sm" />
  if (!data) return <Text c="dimmed">The rankings aren’t available.</Text>
  const labels = data.season_labels
  const mine = 'var(--mantine-primary-color-light)'
  return (
    <Stack>
      <Text size="sm" c="dimmed">
        A country’s place in this ranking (the sum of its last five seasons) decides how many clubs it sends to Europe and in which rounds, two seasons later. The two countries with the
        best season also get an extra Champions League place each (a European Performance Spot).
      </Text>
      <Card withBorder padding="sm">
        <Title order={4} mb="xs">
          Country ranking
        </Title>
        <Table.ScrollContainer minWidth={0}>
          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>#</Table.Th>
                <Table.Th>Country</Table.Th>
                {labels.map((l, i) => (
                  <Table.Th key={l} ta="right" visibleFrom={i < labels.length - 2 ? 'sm' : undefined} style={{ whiteSpace: 'nowrap' }}>
                    {l}
                    {i === labels.length - 1 && data.in_progress && (
                      <Text span size="xs" c="dimmed" display="block">
                        so far
                      </Text>
                    )}
                  </Table.Th>
                ))}
                <Table.Th ta="right">Total</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.countries.map((c) => (
                <Table.Tr key={c.nation} bg={c.nation === userNation ? mine : undefined} fw={c.nation === userNation ? 700 : undefined}>
                  <Table.Td>{c.rank}</Table.Td>
                  <Table.Td style={{ whiteSpace: 'nowrap' }}>{nationName(c.nation, c.name)}</Table.Td>
                  {c.seasons.map((v, i) => (
                    <Table.Td key={i} ta="right" visibleFrom={i < c.seasons.length - 2 ? 'sm' : undefined}>
                      {num(v)}
                    </Table.Td>
                  ))}
                  <Table.Td ta="right" fw={700}>
                    {num(c.total)}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
      <Card withBorder padding="sm">
        <Title order={4} mb="xs">
          Club coefficients
        </Title>
        <Table.ScrollContainer minWidth={0}>
          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>#</Table.Th>
                <Table.Th>Club</Table.Th>
                <Table.Th>Country</Table.Th>
                <Table.Th ta="right">Coefficient</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.clubs.map((c) => (
                <Table.Tr key={c.club.id} bg={c.club.id === userId ? mine : undefined} fw={c.club.id === userId ? 700 : undefined}>
                  <Table.Td>{c.rank}</Table.Td>
                  <Table.Td style={{ whiteSpace: 'nowrap' }}>
                    <ClubLink club={c.club} />
                  </Table.Td>
                  <Table.Td style={{ whiteSpace: 'nowrap' }}>{nationName(c.nation)}</Table.Td>
                  <Table.Td ta="right">{num(c.coefficient)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Card>
    </Stack>
  )
}
