import { Badge, Card, Grid, Group, Loader, Stack, Table, Text, Title } from '@mantine/core'
import { useParams } from '@tanstack/react-router'

import { useMatch } from '../api/hooks'
import type { MatchEvent, PlayerLine } from '../api/types'
import MatchStats from '../components/MatchStats'
import { longDate, matchRatingColor, score, stageLabel } from '../lib/format'

const EVENT_LABEL: Record<string, string> = {
  goal: '⚽ Goal',
  penalty_goal: '⚽ Penalty',
  own_goal: '⚽ Own goal',
  penalty_miss: '✗ Penalty missed',
  yellow: '🟨 Booked',
  red: '🟥 Sent off',
  sub: '⇄ Substitution',
  injury: '✚ Injury',
}

export default function MatchReportPage() {
  const { fixtureId } = useParams({ from: '/match/$fixtureId' })
  const match = useMatch(Number(fixtureId))
  if (match.isPending) return <Loader />
  if (!match.data) return <Text c="red">{match.error?.message}</Text>
  const { fixture, events, stats } = match.data

  return (
    <Stack>
      <Card withBorder>
        <Stack gap={2} align="center">
          <Text size="sm" c="dimmed">
            {fixture.competition_name} · {stageLabel(fixture.stage, fixture.round, fixture.tie, fixture.leg)} · {longDate(fixture.date)}
          </Text>
          <Group gap="xl" wrap="nowrap">
            <Title order={3} ta="right" style={{ flex: 1 }}>
              {fixture.home.name}
            </Title>
            <Title order={1}>{score(fixture)}</Title>
            <Title order={3} style={{ flex: 1 }}>
              {fixture.away.name}
            </Title>
          </Group>
        </Stack>
      </Card>
      <Grid>
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Card withBorder h="100%">
            <Text fw={600} mb="xs">
              Events
            </Text>
            <Stack gap={4}>
              {events.length === 0 && <Text size="sm">A quiet game.</Text>}
              {events.map((e, i) => (
                <EventRow key={i} event={e} homeId={fixture.home.id} />
              ))}
            </Stack>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Card withBorder h="100%">
            <Text fw={600} mb="xs">
              Statistics
            </Text>
            {stats ? <MatchStats home={stats.home} away={stats.away} /> : <Text size="sm">No statistics recorded.</Text>}
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Lineup title={fixture.home.name} lines={match.data.home_lines} />
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Lineup title={fixture.away.name} lines={match.data.away_lines} />
        </Grid.Col>
      </Grid>
    </Stack>
  )
}

function EventRow({ event, homeId }: { event: MatchEvent; homeId: number }) {
  const home = event.club_id === homeId
  let text = event.player ?? ''
  if (event.type === 'goal' && event.other_player) text += ` (assist ${event.other_player})`
  if (event.type === 'sub') text = `${event.other_player ?? ''} on for ${event.player ?? ''}`
  if (event.type === 'injury' || (event.type === 'red' && event.detail)) text += ` – ${event.detail}`
  return (
    <Group gap="xs" wrap="nowrap" justify={home ? 'flex-start' : 'flex-end'}>
      {home && <Badge variant="light" miw={46} px={4}>{event.label}</Badge>}
      <Text size="sm" ta={home ? 'left' : 'right'}>
        <b>{EVENT_LABEL[event.type] ?? event.type}</b> {text}
      </Text>
      {!home && <Badge variant="light" color="red" miw={46} px={4}>{event.label}</Badge>}
    </Group>
  )
}

function Lineup({ title, lines }: { title: string; lines: PlayerLine[] }) {
  return (
    <Card withBorder>
      <Text fw={600} mb="xs">
        {title}
      </Text>
      <Table verticalSpacing={2}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Player</Table.Th>
            <Table.Th ta="right">Min</Table.Th>
            <Table.Th ta="right">G</Table.Th>
            <Table.Th ta="right">A</Table.Th>
            <Table.Th ta="right">Sh (OT)</Table.Th>
            <Table.Th ta="right">Pass</Table.Th>
            <Table.Th ta="right">Tkl</Table.Th>
            <Table.Th ta="right">Int</Table.Th>
            <Table.Th ta="right">Rating</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {lines.map((l) => (
            <Table.Tr key={l.player_id} c={l.started ? undefined : 'dimmed'}>
              <Table.Td>
                {l.name}
                {l.yellow > 0 && ' 🟨'}
                {l.red > 0 && ' 🟥'}
              </Table.Td>
              <Table.Td ta="right">{l.minutes}</Table.Td>
              <Table.Td ta="right">{l.goals || ''}</Table.Td>
              <Table.Td ta="right">{l.assists || ''}</Table.Td>
              <Table.Td ta="right">
                {l.shots} ({l.shots_on_target})
              </Table.Td>
              <Table.Td ta="right">
                {l.passes_completed}/{l.passes}
              </Table.Td>
              <Table.Td ta="right">{l.tackles}</Table.Td>
              <Table.Td ta="right">{l.interceptions}</Table.Td>
              <Table.Td ta="right">
                <Text span fw={700} c={matchRatingColor(l.rating)}>
                  {l.rating.toFixed(1)}
                </Text>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Card>
  )
}
