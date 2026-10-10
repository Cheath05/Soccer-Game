import { Badge, Group, Progress, SegmentedControl, Stack, Table, Text, Title, UnstyledButton } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'
import { useMemo } from 'react'

import { useCareer, useSquad, useTactics } from '../api/hooks'
import type { SquadPlayer } from '../api/types'
import { SeasonChange } from '../components/SeasonChange'
import { money, positionColor, ratingColor, wage } from '../lib/format'
import { rememberPlayerList } from '../lib/playerList'
import { useUrlState } from '../lib/urlState'

type SortKey = 'position' | 'selection' | 'name' | 'age' | 'overall' | 'condition' | 'form' | 'appearances' | 'goals' | 'value_eur' | 'wage_weekly_eur'

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

export default function SquadPage() {
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
  const [sort, setSort] = useUrlState<{ key: SortKey; desc: boolean }>('sort', { key: 'position', desc: false })

  const rows = useMemo(() => {
    const list = (squad.data ?? []).filter((p) => group === 'All' || GROUPS[group].includes(p.position))
    if (sort.key === 'position') return sort.desc ? [...list].reverse() : list
    const sorted = [...list].sort((a, b) => (sort.key === 'selection' ? (selection.get(a.id) ?? 3) - (selection.get(b.id) ?? 3) || b.overall - a.overall : compare(a, b, sort.key)))
    return sort.desc ? sorted.reverse() : sorted
  }, [squad.data, group, sort, selection])

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Squad</Title>
        <SegmentedControl value={group} onChange={setGroup} data={Object.keys(GROUPS)} />
      </Group>
      <Table.ScrollContainer minWidth={1040}>
        <Table highlightOnHover striped>
          <Table.Thead>
            <Table.Tr>
              {COLUMNS.map((c) => (
                <Table.Th key={c.key} ta={c.numeric ? 'right' : undefined}>
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
              <Table.Th>Contract</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((p) => (
              <Table.Tr key={p.id} style={{ cursor: 'pointer' }} onClick={() => {
                  rememberPlayerList(rows.map((r) => r.id))
                  void navigate({ to: '/players/$playerId', params: { playerId: String(p.id) } })
                }}>
                <Table.Td>
                  <Badge color={positionColor(p.position)} variant="light" w={44}>
                    {p.position}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  {selection.has(p.id) && (
                    <Badge size="sm" variant={selection.get(p.id) === 0 ? 'filled' : 'light'} color={selection.get(p.id) === 2 ? 'gray' : selection.get(p.id) === 1 ? 'teal' : 'blue'} w={72}>
                      {['XI', 'Bench', 'Reserve'][selection.get(p.id) ?? 2]}
                    </Badge>
                  )}
                </Table.Td>
                <Table.Td>
                  <Group gap={6} wrap="nowrap">
                    <Text size="sm" fw={500}>
                      {p.name}
                    </Text>
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
                <Table.Td ta="right">{p.age}</Table.Td>
                <Table.Td ta="right">
                  <Group gap={6} wrap="nowrap" justify="flex-end" component="span" display="inline-flex">
                    <Text fw={700} c={ratingColor(p.overall)} size="sm" span>
                      {p.overall}
                    </Text>
                    <Text span w={44} ta="left">
                      <SeasonChange start={p.season_start_overall} now={p.overall} />
                    </Text>
                  </Group>
                </Table.Td>
                <Table.Td>
                  <Progress value={p.condition} color={p.condition >= 90 ? 'teal' : p.condition >= 75 ? 'yellow' : 'red'} size="sm" />
                </Table.Td>
                <Table.Td ta="right">{p.form.toFixed(1)}</Table.Td>
                <Table.Td ta="right">{p.appearances}</Table.Td>
                <Table.Td ta="right">
                  {p.goals}/{p.assists}
                </Table.Td>
                <Table.Td ta="right">{money(p.value_eur)}</Table.Td>
                <Table.Td ta="right">{wage(p.wage_weekly_eur)}</Table.Td>
                <Table.Td>{p.contract_end.slice(0, 4)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Stack>
  )
}

function compare(a: SquadPlayer, b: SquadPlayer, key: Exclude<SortKey, 'selection'>): number {
  const x = a[key]
  const y = b[key]
  if (typeof x === 'number' && typeof y === 'number') return x - y
  return String(x).localeCompare(String(y))
}
