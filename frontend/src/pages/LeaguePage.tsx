import { Badge, Group, Select, Stack, Table, Text, Title } from '@mantine/core'
import { useState } from 'react'

import { useCareer, useClubHistory, useCompetitions, useSeasons, useTable } from '../api/hooks'
import ClubLink from '../components/ClubLink'
import LeaguePicker from '../components/LeaguePicker'
import { OUTCOMES, longDate } from '../lib/format'

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
  const [seasonId, setSeasonId] = useState<string | null>(null)
  const seasons = useSeasons().data ?? []
  const history = useClubHistory(career?.club.id).data
  // Between seasons, until the new one's first league match is played, the last finished
  // season's final table shows (of the league the user's club played in then, as that is the
  // table it finished in) until a season or league is picked.
  const current = seasons.find((s) => s.current)
  const previous = seasons.find((s) => !s.current && s.finished !== false)
  const homeKey = career?.competition?.key ?? 'ENG1'
  const unstarted = useTable(key ?? homeKey)
  const waiting = previous !== undefined && unstarted.data?.started === false
  const lastLeague = history?.seasons.find((s) => s.season_id === previous?.id)?.competition.key
  const active = key ?? (waiting && !seasonId && lastLeague ? lastLeague : homeKey)
  const shownId = seasonId ? Number(seasonId) : waiting ? previous.id : current?.id
  const table = useTable(active, shownId === undefined || shownId === current?.id ? null : shownId)

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>
          {table.data?.name ?? 'League'}
          {table.data && seasons.length > 1 && (
            <Text span c="dimmed" fz="lg" ml="xs">
              {table.data.season}
              {table.data.final ? ' · final table' : ''}
            </Text>
          )}
        </Title>
        <Group>
          {seasons.length > 1 && (
            <Select
              aria-label="Season"
              w={130}
              value={String(shownId ?? '')}
              onChange={setSeasonId}
              allowDeselect={false}
              data={seasons.map((s) => ({ value: String(s.id), label: s.current ? `${s.label} (now)` : s.label }))}
            />
          )}
          {competitions.data && <LeaguePicker leagues={competitions.data} value={active} onChange={setKey} />}
        </Group>
      </Group>
      {waiting && shownId === previous.id && (
        <Text size="sm" c="dimmed">
          Last season&apos;s final table
          {unstarted.data?.first_match ? `: the ${unstarted.data.season} season starts on ${longDate(unstarted.data.first_match)}.` : '.'}
        </Text>
      )}
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
                  <Group gap="xs" wrap="nowrap">
                    <ClubLink club={r.club} />
                    {r.outcome && OUTCOMES[r.outcome] && (
                      <Badge size="xs" variant="light" color={OUTCOMES[r.outcome]!.color}>
                        {OUTCOMES[r.outcome]!.label}
                      </Badge>
                    )}
                  </Group>
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
