import { Badge, Button, Card, Grid, Group, Loader, SegmentedControl, SimpleGrid, Stack, Table, Text, Title, UnstyledButton } from '@mantine/core'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useMemo, useState } from 'react'

import { useClub, useClubPlayers } from '../api/hooks'
import type { ClubPlayer, Fixture } from '../api/types'
import ClubLink from '../components/ClubLink'
import Overall from '../components/Overall'
import ResultBadge from '../components/ResultBadge'
import { money, positionColor, score, shortDate, wage } from '../lib/format'

type SortKey = 'position' | 'name' | 'age' | 'overall' | 'form' | 'appearances' | 'goals' | 'value_eur' | 'contract_end'

const GROUPS: Record<string, string[]> = {
  All: [],
  GK: ['GK'],
  DEF: ['CB', 'LB', 'RB', 'LWB', 'RWB'],
  MID: ['DM', 'CM', 'AM', 'LM', 'RM'],
  ATT: ['LW', 'RW', 'ST'],
}

const COLUMNS: { key: SortKey; label: string; numeric?: boolean }[] = [
  { key: 'position', label: 'Pos' },
  { key: 'name', label: 'Name' },
  { key: 'age', label: 'Age', numeric: true },
  { key: 'overall', label: 'OVR', numeric: true },
  { key: 'form', label: 'Form', numeric: true },
  { key: 'appearances', label: 'Apps', numeric: true },
  { key: 'goals', label: 'Goals', numeric: true },
  { key: 'value_eur', label: 'Value', numeric: true },
  { key: 'contract_end', label: 'Contract' },
]

const STATUS: Record<ClubPlayer['status'], { label: string; color: string } | null> = {
  available: null,
  injured: { label: 'INJ', color: 'red' },
  suspended: { label: 'SUS', color: 'orange' },
}

export default function ClubPage() {
  const { clubId } = useParams({ from: '/clubs/$clubId' })
  const id = Number(clubId)
  const club = useClub(id)
  const players = useClubPlayers(id)
  const navigate = useNavigate()
  const [group, setGroup] = useState('All')
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'position', desc: false })

  const rows = useMemo(() => {
    const list = (players.data ?? []).filter((p) => group === 'All' || GROUPS[group].includes(p.position))
    if (sort.key === 'position') return sort.desc ? [...list].reverse() : list
    const sorted = [...list].sort((a, b) => compare(a, b, sort.key))
    return sort.desc ? sorted.reverse() : sorted
  }, [players.data, group, sort])

  if (club.isPending) return <Loader />
  if (!club.data) return <Text c="red">{club.error?.message}</Text>
  const c = club.data

  return (
    <Stack>
      <Group justify="space-between" align="start">
        <div>
          <Group gap="xs">
            <Title order={2}>{c.club.name}</Title>
            {c.own_club && <Badge variant="light">Your club</Badge>}
          </Group>
          <Text c="dimmed">
            {[c.competition?.name, c.nation, c.stadium_name && `${c.stadium_name}${c.stadium_capacity ? ` (${c.stadium_capacity.toLocaleString('en-GB')})` : ''}`]
              .filter(Boolean)
              .join(' · ')}
          </Text>
        </div>
        {c.own_club && (
          <Button variant="light" onClick={() => void navigate({ to: '/squad' })}>
            Manage your squad
          </Button>
        )}
      </Group>

      <SimpleGrid cols={{ base: 2, sm: 4 }}>
        <Fact label="League position" value={c.position ? ordinal(c.position) : '–'} note={c.position ? `${c.points} pts from ${c.played} ${c.played === 1 ? 'game' : 'games'}` : 'Season not started'} />
        <Fact label="Squad" value={`${c.squad_size} players`} note={`Average age ${c.average_age.toFixed(1)} · OVR ${c.average_overall.toFixed(1)}`} />
        <Fact label="Manager" value={c.manager ?? '–'} note={c.own_club ? 'You' : 'Not yet in the game'} />
        <Fact label="Reputation" value={String(c.reputation)} />
        <Fact label="Wage bill" value={`${c.own_club ? '' : '≈ '}${wage(c.wage_bill_weekly_eur)}`} note={c.own_club ? undefined : 'Estimate'} />
        <Fact label="Transfer budget" value={`≈ ${money(c.budget_estimate_eur)}`} note="Estimate from wages and reputation" />
        <Fact label="Best player" value={c.top_players[0]?.name ?? '–'} note={c.top_players[0] ? `${c.top_players[0].position} · ${c.top_players[0].overall} OVR` : undefined} />
        <Fact label="Recent transfers" value="None yet" note="Transfers aren't in the game yet" />
      </SimpleGrid>

      <Grid>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <FixtureCard title="Recent results" fixtures={c.recent} clubId={id} empty="No matches played yet." />
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <FixtureCard title="Next fixtures" fixtures={c.upcoming} clubId={id} empty="No fixtures left this season." />
        </Grid.Col>
      </Grid>

      <Group justify="space-between">
        <Title order={3}>Squad</Title>
        <SegmentedControl value={group} onChange={setGroup} data={Object.keys(GROUPS)} />
      </Group>
      <Table.ScrollContainer minWidth={760}>
        <Table highlightOnHover striped>
          <Table.Thead>
            <Table.Tr>
              {COLUMNS.map((col) => (
                <Table.Th key={col.key} ta={col.numeric ? 'right' : undefined}>
                  <UnstyledButton fw={600} fz="sm" onClick={() => setSort((s) => ({ key: col.key, desc: s.key === col.key ? !s.desc : !!col.numeric }))}>
                    {col.label}
                    {sort.key === col.key ? (sort.desc ? ' ▾' : ' ▴') : ''}
                  </UnstyledButton>
                </Table.Th>
              ))}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((p) => (
              <Table.Tr key={p.id} style={{ cursor: 'pointer' }} onClick={() => void navigate({ to: '/players/$playerId', params: { playerId: String(p.id) } })}>
                <Table.Td>
                  <Badge color={positionColor(p.position)} variant="light" w={44}>
                    {p.position}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Group gap={6} wrap="nowrap">
                    <Text size="sm" fw={500}>
                      {p.name}
                    </Text>
                    {STATUS[p.status] && (
                      <Badge color={STATUS[p.status]!.color} size="xs">
                        {STATUS[p.status]!.label}
                      </Badge>
                    )}
                  </Group>
                </Table.Td>
                <Table.Td ta="right">{p.age}</Table.Td>
                <Table.Td ta="right">
                  <Overall value={p.overall} trend={p.trend} />
                </Table.Td>
                <Table.Td ta="right">{p.form.toFixed(1)}</Table.Td>
                <Table.Td ta="right">{p.appearances}</Table.Td>
                <Table.Td ta="right">{p.goals}</Table.Td>
                <Table.Td ta="right">{money(p.value_eur)}</Table.Td>
                <Table.Td>{p.contract_end.slice(0, 4)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Stack>
  )
}

function Fact({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <Card withBorder padding="sm">
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text fw={700} size="lg" lineClamp={1}>
        {value}
      </Text>
      {note && (
        <Text size="xs" c="dimmed">
          {note}
        </Text>
      )}
    </Card>
  )
}

function FixtureCard({ title, fixtures, clubId, empty }: { title: string; fixtures: Fixture[]; clubId: number; empty: string }) {
  const navigate = useNavigate()
  return (
    <Card withBorder padding="sm">
      <Text fw={600} mb={4}>
        {title}
      </Text>
      {fixtures.length === 0 ? (
        <Text size="sm" c="dimmed">
          {empty}
        </Text>
      ) : (
        <Table verticalSpacing={2}>
          <Table.Tbody>
            {fixtures.map((f) => {
              const home = f.home.id === clubId
              const opponent = home ? f.away : f.home
              const played = f.status === 'played'
              return (
                <Table.Tr
                  key={f.id}
                  style={{ cursor: played ? 'pointer' : undefined }}
                  onClick={() => played && void navigate({ to: '/match/$fixtureId', params: { fixtureId: String(f.id) } })}
                >
                  <Table.Td w={70}>{shortDate(f.date)}</Table.Td>
                  <Table.Td w={24}>{f.neutral ? 'N' : home ? 'H' : 'A'}</Table.Td>
                  <Table.Td>
                    <ClubLink club={opponent} />
                  </Table.Td>
                  <Table.Td ta="right">{played ? score(f) : ''}</Table.Td>
                  <Table.Td w={36}>
                    <ResultBadge fixture={f} clubId={clubId} />
                  </Table.Td>
                </Table.Tr>
              )
            })}
          </Table.Tbody>
        </Table>
      )}
    </Card>
  )
}

function ordinal(n: number): string {
  const suffix = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th'
  return `${n}${suffix}`
}

function compare(a: ClubPlayer, b: ClubPlayer, key: SortKey): number {
  const x = a[key]
  const y = b[key]
  if (typeof x === 'number' && typeof y === 'number') return x - y
  return String(x).localeCompare(String(y))
}
