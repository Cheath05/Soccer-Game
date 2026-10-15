import { Badge, Card, Grid, Group, SegmentedControl, Select, Stack, Table, Text, Title } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import type { Career, EuropeLeaguePhase, EuropeMatchday, Fixture } from '../../api/types'
import { useDevice } from '../../lib/device'
import { ordinal, score } from '../../lib/format'
import ClubLink from '../ClubLink'
import { FixtureLink, Swatch } from './Pieces'
import { ZONES, dateList, dayDate, fixtureTarget } from './shared'

/** The matchday to show to start with: the first one with a match still to play, or the last. */
function nextMatchday(matchdays: EuropeMatchday[]): number {
  const drawn = matchdays.filter((m) => m.fixtures.length > 0)
  const open = drawn.find((m) => m.fixtures.some((f) => f.status !== 'played'))
  return (open ?? drawn[drawn.length - 1])?.round ?? 1
}

/** The league phase: its 36-club table with the zones (straight to the round of 16, the knockout
 * play-off, out), and a matchday at a time. Before the draw, when it will be and when it starts. */
export default function LeaguePhase({
  phase,
  qualifyingDrawn,
  userId,
  career,
}: {
  phase: EuropeLeaguePhase
  qualifyingDrawn: boolean
  userId: number | undefined
  career: Career | undefined
}) {
  const { phone } = useDevice()
  const [picked, setPicked] = useState<number | null>(null)
  const first = phase.matchdays[0]?.dates[0]
  const last = phase.matchdays[phase.matchdays.length - 1]?.dates.slice(-1)[0]
  const [po1, po2] = phase.to_playoff
  const matchday = picked ?? nextMatchday(phase.matchdays)
  const shown = phase.matchdays.find((m) => m.round === matchday)
  const zoneEnd = (position: number) => position === phase.to_round_of_16 || position === po2

  if (!phase.drawn) {
    return (
      <Card withBorder padding="sm">
        <Title order={4}>League phase</Title>
        <Text size="sm" c="dimmed" mt={4}>
          {qualifyingDrawn ? 'Drawn once the play-off round is over.' : 'Drawn after the summer play-off round.'} {phase.matches} matches each
          {first ? `, from ${dateList([first])}${last ? ` to ${dateList([last])}` : ''}` : ''}.
        </Text>
      </Card>
    )
  }

  return (
    <Card withBorder padding="sm">
      <Group justify="space-between" align="baseline" mb={4}>
        <Title order={4}>League phase</Title>
        <Text size="sm" c="dimmed">
          {phase.matches} matches each{phase.final ? ' · final table' : ''}
        </Text>
      </Group>
      <Grid gap="lg">
        <Grid.Col span={{ base: 12, lg: 7 }}>
          <Table.ScrollContainer minWidth={phone ? 0 : 600}>
            <Table highlightOnHover verticalSpacing={phone ? 6 : 6} aria-label="League phase table">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>#</Table.Th>
                  <Table.Th>Club</Table.Th>
                  <Table.Th ta="right">P</Table.Th>
                  <Table.Th ta="right" visibleFrom="sm">
                    W
                  </Table.Th>
                  <Table.Th ta="right" visibleFrom="sm">
                    D
                  </Table.Th>
                  <Table.Th ta="right" visibleFrom="sm">
                    L
                  </Table.Th>
                  <Table.Th ta="right" visibleFrom="sm">
                    GF
                  </Table.Th>
                  <Table.Th ta="right" visibleFrom="sm">
                    GA
                  </Table.Th>
                  <Table.Th ta="right">GD</Table.Th>
                  <Table.Th ta="right">Pts</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {phase.table.map((r) => {
                  const zone = ZONES[r.zone]
                  const mine = r.club.id === userId
                  return (
                    <Table.Tr
                      key={r.club.id}
                      bg={`var(--mantine-color-${zone.color}-light)`}
                      fw={mine ? 700 : undefined}
                      style={zoneEnd(r.position) ? { borderBottom: '2px solid var(--mantine-color-dimmed)' } : undefined}
                    >
                      <Table.Td style={{ boxShadow: `inset 4px 0 0 var(--mantine-color-${zone.color}-6)` }} title={zone.label}>
                        {r.position}
                      </Table.Td>
                      <Table.Td>
                        <Group gap="xs" wrap="nowrap">
                          <div style={{ minWidth: 0 }}>
                            <ClubLink club={r.club} />
                            <Text size="xs" c="dimmed" fw={400} hiddenFrom="sm">
                              W {r.won} · D {r.drawn} · L {r.lost} · {r.goals_for}–{r.goals_against}
                            </Text>
                          </div>
                          {mine && (
                            <Badge size="xs" variant="filled">
                              You
                            </Badge>
                          )}
                        </Group>
                      </Table.Td>
                      <Table.Td ta="right">{r.played}</Table.Td>
                      <Table.Td ta="right" visibleFrom="sm">
                        {r.won}
                      </Table.Td>
                      <Table.Td ta="right" visibleFrom="sm">
                        {r.drawn}
                      </Table.Td>
                      <Table.Td ta="right" visibleFrom="sm">
                        {r.lost}
                      </Table.Td>
                      <Table.Td ta="right" visibleFrom="sm">
                        {r.goals_for}
                      </Table.Td>
                      <Table.Td ta="right" visibleFrom="sm">
                        {r.goals_against}
                      </Table.Td>
                      <Table.Td ta="right">{r.goal_difference > 0 ? `+${r.goal_difference}` : r.goal_difference}</Table.Td>
                      <Table.Td ta="right" fw={700}>
                        {r.points}
                      </Table.Td>
                    </Table.Tr>
                  )
                })}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          <Group gap="md" mt="xs">
            <Swatch color={ZONES.round_of_16.color} label={`${ordinal(1)}–${ordinal(phase.to_round_of_16)}: ${ZONES.round_of_16.label}`} />
            <Swatch color={ZONES.playoff.color} label={`${ordinal(po1)}–${ordinal(po2)}: ${ZONES.playoff.label}`} />
            <Swatch color={ZONES.out.color} label={`${ordinal(po2 + 1)}–${ordinal(phase.table.length)}: ${ZONES.out.label}`} />
          </Group>
        </Grid.Col>
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <Group justify="space-between" mb="xs" gap="xs">
            <Title order={5}>Matches</Title>
            {phone ? (
              <Select
                aria-label="Matchday"
                w={150}
                value={String(matchday)}
                onChange={(v) => v && setPicked(Number(v))}
                allowDeselect={false}
                data={phase.matchdays.map((m) => ({ value: String(m.round), label: `Matchday ${m.round}` }))}
              />
            ) : (
              <Group gap="xs">
                <Text size="sm" c="dimmed">
                  Matchday
                </Text>
                <SegmentedControl
                  aria-label="Matchday"
                  value={String(matchday)}
                  onChange={(v) => setPicked(Number(v))}
                  data={phase.matchdays.map((m) => ({ value: String(m.round), label: String(m.round) }))}
                />
              </Group>
            )}
          </Group>
          {shown && (
            <>
              <Text size="xs" c="dimmed" mb={4}>
                {dateList(shown.dates)}
              </Text>
              <Matchday fixtures={shown.fixtures} userId={userId} career={career} />
            </>
          )}
        </Grid.Col>
      </Grid>
    </Card>
  )
}

function Matchday({ fixtures, userId, career }: { fixtures: Fixture[]; userId: number | undefined; career: Career | undefined }) {
  const { phone } = useDevice()
  const navigate = useNavigate()
  if (fixtures.length === 0)
    return (
      <Text size="sm" c="dimmed">
        No matches.
      </Text>
    )
  const days = [...new Set(fixtures.map((f) => f.date))].sort()
  const open = (f: Fixture) => {
    const target = fixtureTarget(f, career)
    if (target === 'report') void navigate({ to: '/match/$fixtureId', params: { fixtureId: String(f.id) } })
    else if (target === 'matchday') void navigate({ to: '/matchday' })
  }
  const style = (f: Fixture) => ({ cursor: fixtureTarget(f, career) ? 'pointer' : undefined })
  const isMine = (f: Fixture) => userId !== undefined && (f.home.id === userId || f.away.id === userId)

  if (phone) {
    return (
      <Stack gap="xs">
        {days.map((day) => (
          <div key={day}>
            <Text size="xs" fw={600} c="dimmed" mb={2}>
              {dayDate(day)}
            </Text>
            {fixtures
              .filter((f) => f.date === day)
              .map((f) => {
                const played = f.status === 'played'
                return (
                  <div
                    key={f.id}
                    onClick={() => open(f)}
                    style={{
                      ...style(f),
                      display: 'grid',
                      gridTemplateColumns: 'minmax(0, 1fr) auto',
                      columnGap: 8,
                      alignItems: 'center',
                      padding: '4px 6px',
                      borderBottom: '1px solid var(--mantine-color-default-border)',
                      background: isMine(f) ? 'var(--mantine-primary-color-light)' : undefined,
                      fontWeight: isMine(f) ? 700 : undefined,
                    }}
                  >
                    <div style={{ minWidth: 0 }}>
                      <Text size="sm" truncate>
                        <ClubLink club={f.home} />
                      </Text>
                      <Text size="sm" truncate>
                        <ClubLink club={f.away} />
                      </Text>
                    </div>
                    <Text size="sm" fw={700} ta="center" c={played ? undefined : 'dimmed'}>
                      {played ? (
                        <FixtureLink fixture={f} career={career}>
                          <span style={{ display: 'block' }}>{f.home_goals}</span>
                          <span style={{ display: 'block' }}>{f.away_goals}</span>
                        </FixtureLink>
                      ) : (
                        <FixtureLink fixture={f} career={career}>
                          {fixtureTarget(f, career) === 'matchday' ? 'Play' : '–'}
                        </FixtureLink>
                      )}
                    </Text>
                  </div>
                )
              })}
          </div>
        ))}
      </Stack>
    )
  }

  return (
    <Table.ScrollContainer minWidth={0}>
      <Table highlightOnHover verticalSpacing={6}>
        <Table.Tbody>
          {days.map((day) => [
            <Table.Tr key={day} bg="var(--mantine-color-default-hover)">
              <Table.Td colSpan={3}>
                <Text size="xs" fw={600} c="dimmed">
                  {dayDate(day)}
                </Text>
              </Table.Td>
            </Table.Tr>,
            ...fixtures
              .filter((f) => f.date === day)
              .map((f) => (
                <Table.Tr
                  key={f.id}
                  fw={isMine(f) ? 700 : undefined}
                  bg={isMine(f) ? 'var(--mantine-primary-color-light)' : undefined}
                  style={style(f)}
                  onClick={() => open(f)}
                >
                  <Table.Td ta="right" w="38%">
                    <ClubLink club={f.home} />
                  </Table.Td>
                  <Table.Td ta="center" style={{ whiteSpace: 'nowrap' }} fw={700}>
                    <FixtureLink fixture={f} career={career}>
                      {f.status === 'played' ? score(f) : 'v'}
                    </FixtureLink>
                  </Table.Td>
                  <Table.Td w="38%">
                    <ClubLink club={f.away} />
                  </Table.Td>
                </Table.Tr>
              )),
          ])}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  )
}
