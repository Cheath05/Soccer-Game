import { Badge, Button, Card, Grid, Group, Stack, Table, Text } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'

import { useCareer, useFinances, useSquad, useTable } from '../api/hooks'
import type { Fixture } from '../api/types'
import { Crest } from '../components/PhoneNav'
import ResultBadge from '../components/ResultBadge'
import { confidenceColor, longDate, money, score, shortDate, stageLabel } from '../lib/format'

export default function DashboardPage() {
  const career = useCareer().data
  const table = useTable(career?.competition?.key)
  const squad = useSquad(career?.club.id)
  const finances = useFinances(!!career).data
  const navigate = useNavigate()
  if (!career) return null

  const next = career.next_fixture
  const today = next?.date === career.date
  const rows = table.data?.rows ?? []
  const mine = rows.findIndex((r) => r.club.id === career.club.id)
  const window = rows.slice(Math.max(0, mine - 3), Math.max(0, mine - 3) + 7)
  const unavailable = (squad.data ?? []).filter((p) => p.injury || p.suspended)
  const tired = (squad.data ?? []).filter((p) => !p.injury && p.condition < 80)

  const daysTo = next ? Math.round((Date.parse(next.date) - Date.parse(career.date)) / 86_400_000) : null

  return (
    <Stack gap="sm">
      <Card className="fs-hero" data-matchday={today || undefined} padding="lg">
        <Group justify="space-between" align="center">
          <span className="fs-label">{today ? 'Match day' : 'Next match'}</span>
          {next && !today && daysTo !== null && (
            <Badge variant="light" color="gray">
              in {daysTo} {daysTo === 1 ? 'day' : 'days'}
            </Badge>
          )}
        </Group>
        {next ? (
          <>
            <Group mt="md" justify="space-between" align="flex-start" wrap="nowrap" gap="xs">
              <Side name={next.home.name} mine={next.home.id === career.club.id} />
              <Text className="fs-num" fz={26} c="dimmed" pt={14}>
                V
              </Text>
              <Side name={next.away.name} mine={next.away.id === career.club.id} />
            </Group>
            <Text size="sm" c="dimmed" ta="center" mt="md">
              {longDate(next.date)} · {next.competition_name} · {stageLabel(next.stage, next.round, next.tie, next.leg, next.stage_name)}
            </Text>
            {today ? (
              <Button fullWidth size="md" mt="md" color="orange" onClick={() => void navigate({ to: '/matchday' })}>
                Go to match day
              </Button>
            ) : (
              <Text size="xs" c="dimmed" ta="center" mt={6}>
                Press Continue to advance.
              </Text>
            )}
          </>
        ) : (
          <Text mt="xs">No fixtures scheduled.</Text>
        )}
      </Card>

      <Grid gap="sm">
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Card withBorder h="100%" style={{ cursor: 'pointer' }} onClick={() => void navigate({ to: '/league' })}>
            <Group justify="space-between" align="center">
              <span className="fs-label">{career.competition?.name}</span>
              {career.position && (
                <Text className="fs-num fs-accent" fz={22} lh={1}>
                  {ordinal(career.position)}
                </Text>
              )}
            </Group>
            <Table mt="xs" verticalSpacing={6} withRowBorders={false}>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th w={28} />
                  <Table.Th />
                  <Table.Th ta="right" className="fs-label">P</Table.Th>
                  <Table.Th ta="right" className="fs-label">GD</Table.Th>
                  <Table.Th ta="right" className="fs-label">Pts</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {window.map((r) => {
                  const me = r.club.id === career.club.id
                  return (
                    <Table.Tr key={r.club.id} bg={me ? 'var(--fs-surface-2)' : undefined} fw={me ? 700 : undefined}>
                      <Table.Td c={me ? 'teal' : 'dimmed'} className="fs-num" style={{ borderRadius: '8px 0 0 8px' }}>
                        {r.position}
                      </Table.Td>
                      <Table.Td>{r.club.name}</Table.Td>
                      <Table.Td ta="right" c="dimmed">{r.played}</Table.Td>
                      <Table.Td ta="right" c="dimmed">{r.goal_difference > 0 ? `+${r.goal_difference}` : r.goal_difference}</Table.Td>
                      <Table.Td ta="right" className="fs-num" fz={17} style={{ borderRadius: '0 8px 8px 0' }}>
                        {r.points}
                      </Table.Td>
                    </Table.Tr>
                  )
                })}
              </Table.Tbody>
            </Table>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Card withBorder h="100%">
            <span className="fs-label">Recent results</span>
            <Stack gap={2} mt="xs">
              {career.recent.length === 0 && (
                <Text size="sm" c="dimmed">
                  No matches played yet.
                </Text>
              )}
              {career.recent.map((f: Fixture) => {
                const home = f.home.id === career.club.id
                return (
                  <Group
                    key={f.id}
                    className="fs-row"
                    justify="space-between"
                    wrap="nowrap"
                    gap="xs"
                    py={8}
                    px={6}
                    style={{ cursor: 'pointer' }}
                    onClick={() => void navigate({ to: '/match/$fixtureId', params: { fixtureId: String(f.id) } })}
                  >
                    <ResultBadge fixture={f} clubId={career.club.id} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <Text size="sm" fw={600} truncate>
                        {home ? f.away.name : f.home.name}
                        <Text span c="dimmed" fw={400}>
                          {' '}
                          ({home ? 'H' : 'A'})
                        </Text>
                      </Text>
                      <Text size="xs" c="dimmed" truncate>
                        {shortDate(f.date)} · {f.competition_name}
                      </Text>
                    </div>
                    <Text className="fs-num" fz={20} style={{ whiteSpace: 'nowrap' }}>
                      {score(f)}
                    </Text>
                  </Group>
                )
              })}
            </Stack>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Card withBorder h="100%" style={{ cursor: 'pointer' }} onClick={() => void navigate({ to: '/squad' })}>
            <span className="fs-label">Squad status</span>
            <Stack gap={8} mt="xs">
              {unavailable.length === 0 && tired.length === 0 && (
                <Text size="sm">
                  <Text span c="teal" fw={700}>
                    ●{' '}
                  </Text>
                  Everyone is fit and available.
                </Text>
              )}
              {unavailable.map((p) => (
                <Group key={p.id} justify="space-between" wrap="nowrap">
                  <Text size="sm" truncate>
                    {p.name}
                  </Text>
                  <Badge color="red" variant="light" style={{ flexShrink: 0 }}>
                    {p.injury ? `${p.injury} (back ${shortDate(p.injured_until ?? career.date)})` : `Suspended ${p.suspended}`}
                  </Badge>
                </Group>
              ))}
              {tired.slice(0, 5).map((p) => (
                <Group key={p.id} justify="space-between" wrap="nowrap">
                  <Text size="sm" truncate>
                    {p.name}
                  </Text>
                  <Badge color="yellow" variant="light" style={{ flexShrink: 0 }}>
                    Condition {p.condition}%
                  </Badge>
                </Group>
              ))}
            </Stack>
          </Card>
        </Grid.Col>
        {finances && (
          <Grid.Col span={{ base: 12, md: 6 }}>
            <Card withBorder h="100%" style={{ cursor: 'pointer' }} onClick={() => void navigate({ to: '/finances' })}>
              <Group justify="space-between">
                <span className="fs-label">Finances</span>
                {finances.board && (
                  <Badge color={confidenceColor(finances.board.confidence)} variant="light">
                    Board: {finances.board.mood}
                  </Badge>
                )}
              </Group>
              <Group mt="sm" grow align="flex-start">
                <Figure label="Balance" value={money(finances.balance_eur)} color={finances.balance_eur < 0 ? 'red.5' : undefined} />
                <Figure label="Budget" value={money(finances.budget_eur)} />
                <Figure label="Monthly" value={money(finances.monthly.profit_eur)} color={finances.monthly.profit_eur < 0 ? 'red.5' : 'teal'} />
              </Group>
            </Card>
          </Grid.Col>
        )}
      </Grid>
    </Stack>
  )

}

function Figure({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <div className="fs-label">{label}</div>
      <Text className="fs-num" fz={22} c={color}>
        {value}
      </Text>
    </div>
  )
}

function ordinal(n: number): string {
  const suffix = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] ?? 'th'
  return `${n}${suffix}`
}

function Side({ name, mine }: { name: string; mine: boolean }) {
  return (
    <Stack align="center" gap={8} style={{ flex: 1, minWidth: 0 }}>
      <Crest name={name} size={56} mine={mine} />
      <Text className="fs-num" fz={20} lh={1.1} ta="center" tt="uppercase" lineClamp={2} c={mine ? undefined : 'dark.1'}>
        {name}
      </Text>
    </Stack>
  )
}
