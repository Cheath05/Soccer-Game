import { Badge, Button, Card, Grid, Group, Stack, Table, Text, Title } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'

import { useCareer, useSquad, useTable } from '../api/hooks'
import type { Fixture } from '../api/types'
import ClubLink from '../components/ClubLink'
import ResultBadge from '../components/ResultBadge'
import { longDate, score, shortDate, stageLabel } from '../lib/format'

export default function DashboardPage() {
  const career = useCareer().data
  const table = useTable(career?.competition?.key)
  const squad = useSquad(career?.club.id)
  const navigate = useNavigate()
  if (!career) return null

  const next = career.next_fixture
  const today = next?.date === career.date
  const rows = table.data?.rows ?? []
  const mine = rows.findIndex((r) => r.club.id === career.club.id)
  const window = rows.slice(Math.max(0, mine - 3), Math.max(0, mine - 3) + 7)
  const unavailable = (squad.data ?? []).filter((p) => p.injury || p.suspended)
  const tired = (squad.data ?? []).filter((p) => !p.injury && p.condition < 80)

  return (
    <Stack>
      <Title order={2}>Dashboard</Title>
      <Grid>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Card withBorder h="100%">
            <Text c="dimmed" size="sm">
              Next match
            </Text>
            {next ? (
              <Stack gap="xs" mt="xs">
                <Text fw={700} size="lg">
                  <ClubLink club={next.home} /> v <ClubLink club={next.away} />
                </Text>
                <Text size="sm">
                  {longDate(next.date)} · {next.competition_name} · {stageLabel(next.stage, next.round, next.tie, next.leg, next.stage_name)}
                </Text>
                {today ? (
                  <Button color="orange" onClick={() => void navigate({ to: '/matchday' })}>
                    Go to match day
                  </Button>
                ) : (
                  <Text size="sm" c="dimmed">
                    Press Continue to advance to match day.
                  </Text>
                )}
              </Stack>
            ) : (
              <Text mt="xs">No fixtures scheduled.</Text>
            )}
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Card withBorder h="100%">
            <Group justify="space-between">
              <Text c="dimmed" size="sm">
                {career.competition?.name}
              </Text>
              {career.position && <Badge size="lg">{ordinal(career.position)}</Badge>}
            </Group>
            <Table mt="xs" verticalSpacing={4}>
              <Table.Tbody>
                {window.map((r) => (
                  <Table.Tr key={r.club.id} fw={r.club.id === career.club.id ? 700 : undefined}>
                    <Table.Td w={30}>{r.position}</Table.Td>
                    <Table.Td>
                      <ClubLink club={r.club} />
                    </Table.Td>
                    <Table.Td ta="right">{r.played}</Table.Td>
                    <Table.Td ta="right">{r.goal_difference > 0 ? `+${r.goal_difference}` : r.goal_difference}</Table.Td>
                    <Table.Td ta="right" fw={700}>
                      {r.points}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Card withBorder h="100%">
            <Text c="dimmed" size="sm">
              Recent results
            </Text>
            <Stack gap={6} mt="xs">
              {career.recent.length === 0 && <Text size="sm">No matches played yet.</Text>}
              {career.recent.map((f: Fixture) => (
                <Group key={f.id} justify="space-between" wrap="nowrap" style={{ cursor: 'pointer' }} onClick={() => void navigate({ to: '/match/$fixtureId', params: { fixtureId: String(f.id) } })}>
                  <Text size="sm" w={60} c="dimmed">
                    {shortDate(f.date)}
                  </Text>
                  <Text size="sm" style={{ flex: 1 }} truncate>
                    {f.home.name} {score(f)} {f.away.name}
                  </Text>
                  <ResultBadge fixture={f} clubId={career.club.id} />
                </Group>
              ))}
            </Stack>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Card withBorder h="100%">
            <Text c="dimmed" size="sm">
              Squad status
            </Text>
            <Stack gap={6} mt="xs">
              {unavailable.length === 0 && tired.length === 0 && <Text size="sm">Everyone is fit and available.</Text>}
              {unavailable.map((p) => (
                <Group key={p.id} justify="space-between">
                  <Text size="sm">{p.name}</Text>
                  <Badge color="red" variant="light">
                    {p.injury ? `${p.injury} (back ${shortDate(p.injured_until ?? career.date)})` : `Suspended ${p.suspended}`}
                  </Badge>
                </Group>
              ))}
              {tired.slice(0, 5).map((p) => (
                <Group key={p.id} justify="space-between">
                  <Text size="sm">{p.name}</Text>
                  <Badge color="yellow" variant="light">
                    Condition {p.condition}%
                  </Badge>
                </Group>
              ))}
            </Stack>
          </Card>
        </Grid.Col>
      </Grid>
    </Stack>
  )
}

function ordinal(n: number): string {
  const suffix = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] ?? 'th'
  return `${n}${suffix}`
}
