import { Badge, Group, SegmentedControl, Stack, Table, Text, Title } from '@mantine/core'
import { useState } from 'react'

import { useCareer, useCompetitions, useTable } from '../api/hooks'
import ClubLink from '../components/ClubLink'

const ZONE_COLOR: Record<string, string> = {
  champion: 'var(--mantine-color-yellow-light)',
  promotion: 'var(--mantine-color-teal-light)',
  playoff: 'var(--mantine-color-blue-light)',
  relegation: 'var(--mantine-color-red-light)',
}

export default function LeaguePage() {
  const career = useCareer().data
  const competitions = useCompetitions()
  const [key, setKey] = useState<string | null>(null)
  const active = key ?? career?.competition?.key ?? 'ENG1'
  const table = useTable(active)

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>{table.data?.name ?? 'League'}</Title>
        {competitions.data && (
          <SegmentedControl value={active} onChange={setKey} data={competitions.data.map((c) => ({ value: c.key, label: c.name.replace('EFL ', '') }))} />
        )}
      </Group>
      <Table.ScrollContainer minWidth={640}>
        <Table highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>#</Table.Th>
              <Table.Th>Club</Table.Th>
              <Table.Th ta="right">P</Table.Th>
              <Table.Th ta="right">W</Table.Th>
              <Table.Th ta="right">D</Table.Th>
              <Table.Th ta="right">L</Table.Th>
              <Table.Th ta="right">GF</Table.Th>
              <Table.Th ta="right">GA</Table.Th>
              <Table.Th ta="right">GD</Table.Th>
              <Table.Th ta="right">Pts</Table.Th>
              <Table.Th>Form</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {(table.data?.rows ?? []).map((r) => (
              <Table.Tr key={r.club.id} bg={r.zone ? ZONE_COLOR[r.zone] : undefined} fw={r.club.id === career?.club.id ? 700 : undefined}>
                <Table.Td>{r.position}</Table.Td>
                <Table.Td>
                  <ClubLink club={r.club} />
                </Table.Td>
                <Table.Td ta="right">{r.played}</Table.Td>
                <Table.Td ta="right">{r.won}</Table.Td>
                <Table.Td ta="right">{r.drawn}</Table.Td>
                <Table.Td ta="right">{r.lost}</Table.Td>
                <Table.Td ta="right">{r.goals_for}</Table.Td>
                <Table.Td ta="right">{r.goals_against}</Table.Td>
                <Table.Td ta="right">{r.goal_difference > 0 ? `+${r.goal_difference}` : r.goal_difference}</Table.Td>
                <Table.Td ta="right" fw={700}>
                  {r.points}
                </Table.Td>
                <Table.Td>
                  <Group gap={2} wrap="nowrap">
                    {r.form.map((f, i) => (
                      <Badge key={i} size="xs" w={18} px={0} color={f === 'W' ? 'green' : f === 'L' ? 'red' : 'gray'}>
                        {f}
                      </Badge>
                    ))}
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      <Group gap="md">
        <Legend color={ZONE_COLOR.promotion} label="Promotion" />
        <Legend color={ZONE_COLOR.playoff} label="Play-offs" />
        <Legend color={ZONE_COLOR.relegation} label="Relegation" />
      </Group>
    </Stack>
  )
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <Group gap={4}>
      <div style={{ width: 14, height: 14, background: color, borderRadius: 3 }} />
      <Text size="xs">{label}</Text>
    </Group>
  )
}
