import { Badge, Card, Group, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core'
import { Link } from '@tanstack/react-router'

import { useClubWorldCup } from '../api/hooks'
import { longDate } from '../lib/format'
import ClubLink from './ClubLink'

const ORDER = ['UEFA', 'CONMEBOL', 'CONCACAF', 'AFC', 'CAF', 'OFC']

/** The FIFA Club World Cup: before the draw, how it's chosen; after it, the entrants, the
 * groups and the knockout rounds. */
export default function ClubWorldCup() {
  const data = useClubWorldCup().data
  if (!data) return null
  if (data.entrants.length === 0) {
    return (
      <Card withBorder padding="sm">
        <Title order={4} mb={4}>
          FIFA Club World Cup {data.year}
        </Title>
        <Text size="sm">
          32 clubs, in June and July {data.year}, hosted by {data.host}. The draw is on {longDate(data.draw)}: Europe’s twelve are the Champions League winners and the best by
          UEFA’s club coefficient; the other continents’ come from their leagues in the game (by strength and titles) and from guest clubs for the regions without a
          league here (Al Ahly, Mamelodi Sundowns, Urawa, Ulsan, Auckland City and more). Eight groups of four, then the round of 16 to the final.
        </Text>
      </Card>
    )
  }
  const byConfederation = ORDER.map((c) => [c, data.entrants.filter((e) => e.confederation === c)] as const)
  return (
    <Stack>
      <Card withBorder padding="sm" aria-label="Entrants">
        <Title order={4} mb="xs">
          FIFA Club World Cup {data.year}: the 32
        </Title>
        <Stack gap={6}>
          {byConfederation.map(([confederation, clubs]) => (
            <Group key={confederation} gap={6}>
              <Text size="xs" c="dimmed" w={80}>
                {confederation}
              </Text>
              {clubs.map((e) => (
                <Badge key={e.team.id} variant="light" color={e.how === 'Hosts' ? 'yellow' : e.how === 'Guest' ? 'grape' : 'blue'} tt="none" title={e.how}>
                  {e.team.name}
                </Badge>
              ))}
            </Group>
          ))}
        </Stack>
      </Card>
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="sm">
        {data.groups.map((g) => (
          <Card key={g.name} withBorder padding="xs">
            <Text fw={600} size="sm" mb={2}>
              {g.name}
            </Text>
            <Table withRowBorders={false} verticalSpacing={2}>
              <Table.Tbody>
                {g.rows.map((r, i) => (
                  <Table.Tr key={r.team.id} bg={i < 2 && r.played === 3 ? 'var(--mantine-color-teal-light)' : undefined}>
                    <Table.Td>
                      <Text size="sm" truncate>
                        <ClubLink club={r.team} />
                      </Text>
                    </Table.Td>
                    <Table.Td ta="right" className="fs-num">
                      {r.gd > 0 ? `+${r.gd}` : r.gd}
                    </Table.Td>
                    <Table.Td ta="right" className="fs-num" fw={600}>
                      {r.points}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Card>
        ))}
      </SimpleGrid>
      {data.rounds.map((r) => (
        <Card key={r.name} withBorder padding="sm">
          <Title order={5} mb={4}>
            {r.name}
          </Title>
          {r.fixtures.map((f) => (
            <Group key={f.id} justify="space-between" wrap="nowrap" className="fs-row">
              <Text size="sm" truncate>
                <ClubLink club={f.home} /> v <ClubLink club={f.away} />
              </Text>
              {f.status === 'played' ? (
                <Link to="/match/$fixtureId" params={{ fixtureId: String(f.id) }}>
                  <Text className="fs-num" fw={600}>
                    {f.home_goals}–{f.away_goals}
                    {f.home_pens !== null ? ` (${f.home_pens}–${f.away_pens} pens)` : ''}
                  </Text>
                </Link>
              ) : (
                <Text size="sm" c="dimmed">
                  {longDate(f.date)}
                </Text>
              )}
            </Group>
          ))}
        </Card>
      ))}
    </Stack>
  )
}
