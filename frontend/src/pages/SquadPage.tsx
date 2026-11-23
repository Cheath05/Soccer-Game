import { Badge, Button, Card, Group, NativeSelect, Progress, SegmentedControl, Stack, Table, Text, Title, UnstyledButton } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'
import { useMemo } from 'react'

import { MLS_LEAGUE } from '../api/americas'
import { useCareer, useSquad, useTactics } from '../api/hooks'
import type { SquadPlayer } from '../api/types'
import { SeasonChange } from '../components/SeasonChange'
import NextSeasonCard from '../components/NextSeasonCard'
import { CLASS_NAMES, scholarshipLabel } from '../lib/college'
import { money, positionColor, ratingColor, wage } from '../lib/format'
import { rememberPlayerList } from '../lib/playerList'
import { useDevice } from '../lib/device'
import { useUrlState } from '../lib/urlState'

type SortKey = 'position' | 'selection' | 'name' | 'age' | 'overall' | 'condition' | 'form' | 'appearances' | 'goals' | 'value_eur' | 'wage_weekly_eur' | 'class_year' | 'scholarship'

const GROUPS: Record<string, string[]> = {
  All: [],
  GK: ['GK'],
  DEF: ['CB', 'LB', 'RB', 'LWB', 'RWB'],
  MID: ['DM', 'CM', 'AM', 'LM', 'RM'],
  ATT: ['LW', 'RW', 'ST'],
}

const COLUMNS: { key: SortKey; label: string; numeric?: boolean }[] = [
  { key: 'position', label: 'Pos' },
  { key: 'selection', label: 'Team' },
  { key: 'name', label: 'Name' },
  { key: 'age', label: 'Age', numeric: true },
  { key: 'overall', label: 'Ovr', numeric: true },
  { key: 'condition', label: 'Condition', numeric: true },
  { key: 'form', label: 'Form', numeric: true },
  { key: 'appearances', label: 'Apps', numeric: true },
  { key: 'goals', label: 'G/A', numeric: true },
  { key: 'value_eur', label: 'Value', numeric: true },
  { key: 'wage_weekly_eur', label: 'Wage', numeric: true },
]

/** A college player's draft status: declared, may leave early, on the watch, or staying. */
function DraftBadge({ p }: { p: SquadPlayer }) {
  const c = p.college
  if (!c) return null
  const [label, color, title] = c.declared
    ? ['Draft', 'grape', 'Declared for the MLS SuperDraft']
    : c.stay_answer === 'stays'
      ? ['Staying', 'teal', 'Agreed to stay another season']
      : c.draft_risk === 'likely'
        ? ['May leave', 'orange', 'Likely to declare early for the draft after the College Cup: ask him to stay on his page']
        : c.draft_risk === 'possible'
          ? ['Draft watch', 'yellow', 'Could declare early for the draft after the College Cup']
          : [null, '', '']
  if (!label) return null
  return (
    <Badge ml={6} size="xs" color={color} title={title} style={{ flexShrink: 0 }}>
      {label}
    </Badge>
  )
}

// A college coach's squad (W9c) has no values or wages: each player's class and scholarship.
const COLLEGE_COLUMNS = COLUMNS.map((c) =>
  c.key === 'value_eur' ? { key: 'class_year' as SortKey, label: 'Class', numeric: true } : c.key === 'wage_weekly_eur' ? { key: 'scholarship' as SortKey, label: 'Scholarship', numeric: true } : c,
)

const PHONE_HIDDEN: SortKey[] = ['selection', 'age', 'form', 'appearances', 'goals', 'wage_weekly_eur', 'scholarship']

const CLASS_ORDER = ['Fr', 'So', 'Jr', 'Sr']

export default function SquadPage() {
  const { phone } = useDevice()
  const career = useCareer().data
  const squad = useSquad(career?.club.id)
  const navigate = useNavigate()
  const tactics = useTactics().data
  // Who starts, who is on the bench and who is a reserve, as the tactics screen has them.
  const selection = useMemo(() => {
    const map = new Map<number, number>()
    tactics?.reserves.forEach((r) => map.set(r.player_id, 2))
    tactics?.bench.forEach((b) => map.set(b.player_id, 1))
    tactics?.starters.forEach((s) => map.set(s.player_id, 0))
    return map
  }, [tactics])
  const [group, setGroup] = useUrlState('group', 'All')
  // An MLS club's roster rules (designations, the salary budget) are on a page of their own.
  const mlsButton = career?.competition?.key === MLS_LEAGUE && (
    <Button size="xs" variant="light" onClick={() => void navigate({ to: '/mls-roster' })}>
      MLS roster
    </Button>
  )
  const [sort, setSort] = useUrlState<{ key: SortKey; desc: boolean }>('sort', { key: 'position', desc: false })
  const isCollege = !!career?.college
  // A college coach also sees next season: who stays, leaves and joins.
  const [view, setView] = useUrlState('view', 'now')
  const viewSwitch = isCollege && (
    <SegmentedControl size="xs" value={view} onChange={setView} data={[{ value: 'now', label: 'This season' }, { value: 'next', label: 'Next season' }]} aria-label="Season" />
  )
  const columns = isCollege ? COLLEGE_COLUMNS : COLUMNS
  // A player's money, or for a college player his class and scholarship.
  const worth = (p: SquadPlayer) => (p.college ? `${p.college.class_year} · ${scholarshipLabel(p.college.scholarship)}` : money(p.value_eur))

  const rows = useMemo(() => {
    const list = (squad.data ?? []).filter((p) => group === 'All' || GROUPS[group].includes(p.position))
    if (sort.key === 'position') return sort.desc ? [...list].reverse() : list
    const sorted = [...list].sort((a, b) => (sort.key === 'selection' ? (selection.get(a.id) ?? 3) - (selection.get(b.id) ?? 3) || b.overall - a.overall : compare(a, b, sort.key)))
    return sort.desc ? sorted.reverse() : sorted
  }, [squad.data, group, sort, selection])

  const open = (id: number) => {
    rememberPlayerList(rows.map((r) => r.id))
    void navigate({ to: '/players/$playerId', params: { playerId: String(id) } })
  }

  if (isCollege && view === 'next') {
    return (
      <Stack gap="sm">
        <Group justify="space-between" align="center">
          <Title order={2}>Squad</Title>
          {viewSwitch}
        </Group>
        <NextSeasonCard />
      </Stack>
    )
  }

  if (phone) {
    // A phone gets a list of players, not a table: the name, what matters at a glance, the
    // overall as the big number.
    return (
      <Stack gap="sm">
        <Group justify="space-between" align="center" wrap="nowrap">
          <Title order={2}>Squad</Title>
          {mlsButton}
          <NativeSelect
            size="xs"
            aria-label="Sort by"
            value={sort.key}
            onChange={(e) => {
              const key = e.currentTarget.value as SortKey
              setSort({ key, desc: !!columns.find((c) => c.key === key)?.numeric })
            }}
            data={columns.map((c) => ({ value: c.key, label: `Sort: ${c.label === 'Pos' ? 'Position' : c.label === 'Ovr' ? 'Overall' : c.label}` }))}
          />
        </Group>
        {viewSwitch}
        <SegmentedControl fullWidth value={group} onChange={setGroup} data={Object.keys(GROUPS)} />
        <Stack gap={8}>
          {rows.map((p) => {
            const role = selection.get(p.id)
            return (
              <Card key={p.id} className="fs-row" withBorder padding="sm" style={{ cursor: 'pointer' }} onClick={() => open(p.id)}>
                <Group wrap="nowrap" gap="sm">
                  <Badge color={positionColor(p.position)} variant="light" w={46} style={{ flexShrink: 0 }}>
                    {p.position}
                  </Badge>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <Group gap={6} wrap="nowrap">
                      <Text fw={600} truncate>
                        {p.name}
                      </Text>
                      {p.injury && (
                        <Badge color="red" size="xs" style={{ flexShrink: 0 }}>
                          INJ
                        </Badge>
                      )}
                      {p.suspended > 0 && (
                        <Badge color="orange" size="xs" style={{ flexShrink: 0 }}>
                          SUS
                        </Badge>
                      )}
                      <DraftBadge p={p} />
                    </Group>
                    <Text size="xs" c="dimmed" truncate>
                      {p.age}y{role !== undefined ? ` · ${['XI', 'Bench', 'Reserve'][role]}` : ''} · {worth(p)}
                      {p.appearances > 0 ? ` · ${p.goals}/${p.assists} G/A` : ''}
                    </Text>
                    <Progress mt={6} value={p.condition} color={p.condition >= 90 ? 'teal' : p.condition >= 75 ? 'yellow' : 'red'} size={4} aria-label={`Condition ${p.condition}%`} />
                  </div>
                  <Stack gap={0} align="flex-end" style={{ flexShrink: 0 }}>
                    <Text className="fs-num" fz={28} lh={1} c={ratingColor(p.overall)}>
                      {p.overall}
                    </Text>
                    <SeasonChange start={p.season_start_overall} now={p.overall} />
                  </Stack>
                </Group>
              </Card>
            )
          })}
        </Stack>
      </Stack>
    )
  }

  return (
    <Stack>
      <Group justify="space-between">
        <Group gap="sm">
          <Title order={2}>Squad</Title>
          {mlsButton}
          {viewSwitch}
        </Group>
        <SegmentedControl value={group} onChange={setGroup} data={Object.keys(GROUPS)} />
      </Group>
      <Table.ScrollContainer minWidth={phone ? 0 : 1040}>
        <Table highlightOnHover striped>
          <Table.Thead>
            <Table.Tr>
              {columns.map((c) => (
                <Table.Th key={c.key} ta={c.numeric ? 'right' : undefined} visibleFrom={PHONE_HIDDEN.includes(c.key) ? 'sm' : undefined}>
                  <UnstyledButton
                    fw={600}
                    fz="sm"
                    onClick={() => setSort((s) => ({ key: c.key, desc: s.key === c.key ? !s.desc : !!c.numeric }))}
                  >
                    {c.label}
                    {sort.key === c.key ? (sort.desc ? ' ▾' : ' ▴') : ''}
                  </UnstyledButton>
                </Table.Th>
              ))}
              <Table.Th visibleFrom="sm">{isCollege ? 'Leaves' : 'Contract'}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((p) => (
              <Table.Tr key={p.id} style={{ cursor: 'pointer' }} onClick={() => open(p.id)}>
                <Table.Td>
                  <Badge color={positionColor(p.position)} variant="light" w={44}>
                    {p.position}
                  </Badge>
                </Table.Td>
                <Table.Td visibleFrom="sm">
                  {selection.has(p.id) && (
                    <Badge size="sm" variant={selection.get(p.id) === 0 ? 'filled' : 'light'} color={selection.get(p.id) === 2 ? 'gray' : selection.get(p.id) === 1 ? 'teal' : 'blue'} w={72}>
                      {['XI', 'Bench', 'Reserve'][selection.get(p.id) ?? 2]}
                    </Badge>
                  )}
                </Table.Td>
                <Table.Td>
                  <Group gap={6} wrap="nowrap">
                    <div>
                      <Text size="sm" fw={500}>
                        {p.name}
                      </Text>
                      <Text size="xs" c="dimmed" hiddenFrom="sm">
                        {p.age}y{selection.has(p.id) ? ` · ${['XI', 'Bench', 'Reserve'][selection.get(p.id) ?? 2]}` : ''} · {p.goals}/{p.assists} G/A
                      </Text>
                    </div>
                    {p.injury && (
                      <Badge color="red" size="xs">
                        INJ
                      </Badge>
                    )}
                    {p.suspended > 0 && (
                      <Badge color="orange" size="xs">
                        SUS
                      </Badge>
                    )}
                  </Group>
                </Table.Td>
                <Table.Td ta="right" visibleFrom="sm">{p.age}</Table.Td>
                <Table.Td ta="right">
                  <Group gap={6} wrap="nowrap" justify="flex-end" component="span" display="inline-flex">
                    <Text fw={700} c={ratingColor(p.overall)} size="sm" span>
                      {p.overall}
                    </Text>
                    <Text span w={phone ? 20 : 44} ta="left">
                      <SeasonChange start={p.season_start_overall} now={p.overall} />
                    </Text>
                  </Group>
                </Table.Td>
                <Table.Td>
                  <Progress value={p.condition} color={p.condition >= 90 ? 'teal' : p.condition >= 75 ? 'yellow' : 'red'} size="sm" />
                </Table.Td>
                <Table.Td ta="right" visibleFrom="sm">{p.form.toFixed(1)}</Table.Td>
                <Table.Td ta="right" visibleFrom="sm">{p.appearances}</Table.Td>
                <Table.Td ta="right" visibleFrom="sm">
                  {p.goals}/{p.assists}
                </Table.Td>
                {p.college ? (
                  <>
                    <Table.Td ta="right" title={CLASS_NAMES[p.college.class_year]}>
                      {p.college.class_year}
                      <DraftBadge p={p} />
                    </Table.Td>
                    <Table.Td ta="right" visibleFrom="sm">{scholarshipLabel(p.college.scholarship)}</Table.Td>
                    <Table.Td visibleFrom="sm">{p.college.leaves}</Table.Td>
                  </>
                ) : (
                  <>
                    <Table.Td ta="right">{money(p.value_eur)}</Table.Td>
                    <Table.Td ta="right" visibleFrom="sm">{wage(p.wage_weekly_eur)}</Table.Td>
                    <Table.Td visibleFrom="sm">{p.contract_end.slice(0, 4)}</Table.Td>
                  </>
                )}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Stack>
  )
}

function compare(a: SquadPlayer, b: SquadPlayer, key: Exclude<SortKey, 'selection'>): number {
  if (key === 'class_year') return CLASS_ORDER.indexOf(a.college?.class_year ?? '') - CLASS_ORDER.indexOf(b.college?.class_year ?? '')
  if (key === 'scholarship') return (a.college?.scholarship ?? 0) - (b.college?.scholarship ?? 0)
  const x = a[key]
  const y = b[key]
  if (typeof x === 'number' && typeof y === 'number') return x - y
  return String(x).localeCompare(String(y))
}
