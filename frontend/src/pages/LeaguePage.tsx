import { Badge, Group, Select, Stack, Table, Text, Title } from '@mantine/core'

import { useCareer, useClubHistory, useCompetitions, useSeasons, useTable } from '../api/hooks'
import type { TableRow } from '../api/types'
import ClubLink from '../components/ClubLink'
import LeaguePicker from '../components/LeaguePicker'
import { EUROPE_COLOR } from '../lib/competitionColors'
import { OUTCOMES, competitionNation, longDate } from '../lib/format'
import { useDevice } from '../lib/device'
import { useUrlState } from '../lib/urlState'

const ZONE_COLOR: Record<string, string> = {
  champion: 'var(--mantine-color-yellow-light)',
  promotion: 'var(--mantine-color-teal-light)',
  playoff: 'var(--mantine-color-grape-light)',
  relegation: 'var(--mantine-color-red-light)',
}
const ZONE_LABEL: Record<string, string> = { promotion: 'Promotion', playoff: 'Play-offs', relegation: 'Relegation' }

const europeStripe = (competition: string) => `inset 4px 0 0 var(--mantine-color-${EUROPE_COLOR[competition]}-6)`
const europeLight = (competition: string) => `var(--mantine-color-${EUROPE_COLOR[competition]}-light)`

export default function LeaguePage() {
  const { phone } = useDevice()
  const career = useCareer().data
  const competitions = useCompetitions()
  const [key, setKey] = useUrlState<string | null>('league', null)
  const [seasonIdRaw, setSeasonId] = useUrlState<string | null>('season', null)
  const seasonId = seasonIdRaw === null ? null : String(seasonIdRaw)
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

  const rows = table.data?.rows ?? []
  const zones = ['promotion', 'playoff', 'relegation'].filter((z) => rows.some((r) => r.zone === z))
  const places = table.data?.europe_places ?? []
  // A European mark beats the zone colour. The play-off round gets the stripe only.
  const mark = (r: TableRow) => {
    const eu = r.europe && EUROPE_COLOR[r.europe] ? r.europe : null
    if (!eu) return { bg: r.zone ? ZONE_COLOR[r.zone] : undefined, stripe: undefined, title: undefined }
    const playoff = r.europe_stage === 'qualifying'
    const name = places.find((p) => p.competition === eu)?.name ?? eu
    return {
      bg: playoff ? undefined : europeLight(eu),
      stripe: europeStripe(eu),
      title: playoff ? `${name} play-off round` : name,
    }
  }

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
      </Group>
      {competitions.data && (
        <LeaguePicker
          leagues={competitions.data}
          value={active}
          onChange={setKey}
          home={career?.competition ? competitionNation(career.competition) : undefined}
        />
      )}
      {waiting && shownId === previous.id && (
        <Text size="sm" c="dimmed">
          Last season&apos;s final table
          {unstarted.data?.first_match ? `: the ${unstarted.data.season} season starts on ${longDate(unstarted.data.first_match)}.` : '.'}
        </Text>
      )}
      <Table.ScrollContainer minWidth={phone ? 0 : 640}>
        <Table highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>#</Table.Th>
              <Table.Th>Club</Table.Th>
              <Table.Th ta="right">P</Table.Th>
              <Table.Th ta="right" visibleFrom="sm">W</Table.Th>
              <Table.Th ta="right" visibleFrom="sm">D</Table.Th>
              <Table.Th ta="right" visibleFrom="sm">L</Table.Th>
              <Table.Th ta="right" visibleFrom="sm">GF</Table.Th>
              <Table.Th ta="right" visibleFrom="sm">GA</Table.Th>
              <Table.Th ta="right">GD</Table.Th>
              <Table.Th ta="right">Pts</Table.Th>
              <Table.Th visibleFrom="sm">Form</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((r) => (
              <Table.Tr key={r.club.id} bg={mark(r).bg} fw={r.club.id === career?.club.id ? 700 : undefined}>
                <Table.Td style={{ boxShadow: mark(r).stripe }} title={mark(r).title}>
                  {r.position}
                </Table.Td>
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
                <Table.Td ta="right" visibleFrom="sm">{r.won}</Table.Td>
                <Table.Td ta="right" visibleFrom="sm">{r.drawn}</Table.Td>
                <Table.Td ta="right" visibleFrom="sm">{r.lost}</Table.Td>
                <Table.Td ta="right" visibleFrom="sm">{r.goals_for}</Table.Td>
                <Table.Td ta="right" visibleFrom="sm">{r.goals_against}</Table.Td>
                <Table.Td ta="right">{r.goal_difference > 0 ? `+${r.goal_difference}` : r.goal_difference}</Table.Td>
                <Table.Td ta="right" fw={700}>
                  {r.points}
                </Table.Td>
                <Table.Td visibleFrom="sm">
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
      {zones.length > 0 && (
        <Group gap="md">
          {zones.map((z) => (
            <Legend key={z} color={ZONE_COLOR[z]!} label={ZONE_LABEL[z]!} />
          ))}
        </Group>
      )}
      {places.length > 0 && (
        <Stack gap={6}>
          <Text size="sm" fw={600}>
            European places
          </Text>
          <Group gap="xs" style={{ columnGap: 'var(--mantine-spacing-md)' }}>
            {places.map((p) => {
              const playoff = p.stage === 'qualifying'
              return (
                <Group key={`${p.competition}-${p.stage}-${p.how}`} gap={6} wrap="nowrap">
                  <div
                    style={{
                      width: 18,
                      height: 14,
                      flexShrink: 0,
                      borderRadius: 3,
                      background: playoff ? undefined : europeLight(p.competition),
                      boxShadow: europeStripe(p.competition),
                    }}
                  />
                  <Text size="xs">
                    {p.how} · {p.name}
                    {playoff ? ' play-off round' : ''}
                  </Text>
                </Group>
              )
            })}
          </Group>
          <Text size="xs" c="dimmed">
            {table.data?.europe_actual
              ? 'Marked: where each club went in Europe the next season.'
              : 'By finishing position. A club that earns two places takes the higher one, and its other place passes to the next club in the table not already in Europe (for example when the cup winners also finish high). The holders’ places and unused places can give a country more.'}
          </Text>
        </Stack>
      )}
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
