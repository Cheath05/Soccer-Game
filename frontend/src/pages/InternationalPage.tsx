import { Badge, Card, Grid, Group, SegmentedControl, Stack, Table, Text, TextInput, Title } from '@mantine/core'
import { Link } from '@tanstack/react-router'
import { useState } from 'react'

import { useInternational } from '../api/hooks'
import ClubLink from '../components/ClubLink'
import { foldText, longDate } from '../lib/format'

const CONFEDERATIONS = ['All', 'UEFA', 'CONMEBOL', 'CONCACAF', 'AFC', 'CAF', 'OFC']
const SHOWN = 60

/** International football: every national team ranked by its Elo (World Football Elo, moving
 * with every international result), and the latest international matches. */
export default function InternationalPage() {
  const data = useInternational().data
  const [confederation, setConfederation] = useState('All')
  const [search, setSearch] = useState('')
  if (!data) return null
  const needle = foldText(search.trim())
  const teams = data.teams.filter(
    (t) => (confederation === 'All' || t.confederation === confederation) && (!needle || foldText(t.team.name).includes(needle) || t.code.toLowerCase().includes(needle)),
  )
  return (
    <Stack>
      <div>
        <Title order={2}>International</Title>
        <Text c="dimmed" size="sm">
          Every national team, ranked by its Elo rating, which moves with each international result. Squads are called up for FIFA’s international windows, when the
          players are away from their clubs. Qualifiers for the 2030 World Cup and the 2029 Club World Cup are on their way.
        </Text>
      </div>
      <Grid gap="md">
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Card withBorder padding="sm" aria-label="Ranking">
            <Group justify="space-between" mb="xs" gap="xs">
              <Title order={4}>Ranking</Title>
              <TextInput size="xs" placeholder="Find a country" value={search} onChange={(e) => setSearch(e.currentTarget.value)} aria-label="Find a country" />
            </Group>
            <SegmentedControl size="xs" mb="xs" fullWidth value={confederation} onChange={setConfederation} data={CONFEDERATIONS} aria-label="Confederation" />
            <Table.ScrollContainer minWidth={0}>
              <Table highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th w={40}>#</Table.Th>
                    <Table.Th>Team</Table.Th>
                    <Table.Th visibleFrom="sm">Confederation</Table.Th>
                    <Table.Th ta="right">Elo</Table.Th>
                    <Table.Th ta="right">+/−</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {teams.slice(0, needle ? undefined : SHOWN).map((t) => (
                    <Table.Tr key={t.code}>
                      <Table.Td className="fs-num" c="dimmed">
                        {t.rank}
                      </Table.Td>
                      <Table.Td>
                        <ClubLink club={t.team} />
                      </Table.Td>
                      <Table.Td visibleFrom="sm">
                        <Badge size="sm" variant="light" color="gray">
                          {t.confederation}
                        </Badge>
                      </Table.Td>
                      <Table.Td ta="right" className="fs-num">
                        {t.elo}
                      </Table.Td>
                      <Table.Td ta="right" className="fs-num" c={t.change > 0 ? 'teal' : t.change < 0 ? 'red' : 'dimmed'}>
                        {t.change > 0 ? `+${t.change}` : t.change}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
            {!needle && teams.length > SHOWN && (
              <Text size="xs" c="dimmed" mt="xs">
                The top {SHOWN} of {teams.length}: find a country to see the rest.
              </Text>
            )}
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Card withBorder padding="sm" aria-label="Latest results">
            <Title order={4} mb="xs">
              Latest results
            </Title>
            {data.results.length === 0 && (
              <Text size="sm" c="dimmed">
                No international matches yet: the first window is in September.
              </Text>
            )}
            <Stack gap={4}>
              {data.results.map((f) => (
                <Group key={f.id} justify="space-between" wrap="nowrap" className="fs-row">
                  <Text size="sm" truncate>
                    <ClubLink club={f.home} /> v <ClubLink club={f.away} />
                  </Text>
                  <Group gap="xs" wrap="nowrap">
                    <Text size="xs" c="dimmed" visibleFrom="sm">
                      {longDate(f.date)}
                    </Text>
                    <Link to="/match/$fixtureId" params={{ fixtureId: String(f.id) }}>
                      <Text className="fs-num" fw={600}>
                        {f.home_goals}–{f.away_goals}
                      </Text>
                    </Link>
                  </Group>
                </Group>
              ))}
            </Stack>
          </Card>
        </Grid.Col>
      </Grid>
    </Stack>
  )
}
