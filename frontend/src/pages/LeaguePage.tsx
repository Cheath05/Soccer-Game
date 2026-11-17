import { Badge, Card, Group, SegmentedControl, Select, Stack, Table, Text, Title } from '@mantine/core'

import { useCareer, useClubHistory, useCompetitions, usePlayoffs, useSeasons, useTable } from '../api/hooks'
import type { LeaguePlayoff, TableRow } from '../api/types'
import ClubLink from '../components/ClubLink'
import LeaguePicker from '../components/LeaguePicker'
import RoundCard from '../components/RoundCard'
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
  // A league of phases (Apertura, Clausura): the one picked (null: the one under way).
  const [phase, setPhase] = useUrlState<string | null>('phase', null)
  // A league of conferences or zones: their tables, or the whole league's.
  const [view, setView] = useUrlState<string>('view', 'groups')
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
  const pastId = shownId === undefined || shownId === current?.id ? null : shownId
  const table = useTable(active, pastId, phase)
  const playoffs = usePlayoffs(active, pastId).data ?? []
  const shownPhase = table.data?.phase ?? null
  const groups = table.data?.groups ?? []
  const byGroup = groups.length > 0 && view === 'groups' && shownPhase !== 'season'
  const titles = table.data?.titles ?? []
  // The play-offs of the table shown: a phase's own, or the season's.
  const brackets = playoffs.filter((p) => (shownPhase && shownPhase !== 'season' ? p.phase === shownPhase : p.phase === null))

  const rows = table.data?.rows ?? []
  const shownRows = byGroup ? groups.flatMap((g) => g.rows) : rows
  const zones = ['promotion', 'playoff', 'relegation'].filter((z) => shownRows.some((r) => r.zone === z))
  const places = table.data?.europe_places ?? []
  // A European mark beats the zone colour. A qualifying round gets the stripe only.
  const mark = (r: TableRow) => {
    const eu = r.europe && EUROPE_COLOR[r.europe] ? r.europe : null
    if (!eu) return { bg: r.zone ? ZONE_COLOR[r.zone] : undefined, stripe: undefined, title: undefined }
    const playoff = r.europe_stage === 'qualifying'
    // A row doesn't say which round it enters: name it when the competition has only one.
    const same = places.filter((p) => p.competition === eu && p.stage === r.europe_stage)
    const place = same.length === 1 ? same[0] : undefined
    const name = (place ?? places.find((p) => p.competition === eu))?.name ?? eu
    return {
      bg: playoff ? undefined : europeLight(eu),
      stripe: europeStripe(eu),
      title: playoff ? `${name} ${place?.round_name?.toLowerCase() ?? 'qualifying'}` : name,
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
          onChange={(k) => {
            setKey(k)
            setPhase(null)
          }}
          home={career?.competition ? competitionNation(career.competition) : undefined}
        />
      )}
      {((table.data?.phases?.length ?? 0) > 0 || groups.length > 0) && (
        <Group gap="sm">
          {(table.data?.phases?.length ?? 0) > 0 && (
            <SegmentedControl
              aria-label="Tournament"
              value={shownPhase ?? ''}
              onChange={setPhase}
              data={table.data!.phases!.map((p) => ({ value: p.key, label: p.name }))}
            />
          )}
          {groups.length > 0 && shownPhase !== 'season' && (
            <SegmentedControl
              aria-label="Tables"
              value={view}
              onChange={setView}
              data={[
                { value: 'groups', label: groups[0]!.name.includes('Conference') ? 'Conferences' : 'Zones' },
                { value: 'overall', label: 'Overall' },
              ]}
            />
          )}
        </Group>
      )}
      {titles.length > 0 && (
        <Group gap="xs">
          {titles.map((t) => (
            <Badge key={t.title} variant="light" color={t.kind === 'champion' ? 'yellow' : 'blue'} size="lg" tt="none">
              {t.title}: {t.club.name}
            </Badge>
          ))}
        </Group>
      )}
      {waiting && shownId === previous.id && (
        <Text size="sm" c="dimmed">
          Last season&apos;s final table
          {unstarted.data?.first_match ? `: the ${unstarted.data.season} season starts on ${longDate(unstarted.data.first_match)}.` : '.'}
        </Text>
      )}
      {byGroup ? (
        groups.map((g) => (
          <Stack key={g.key} gap={4}>
            <Title order={4}>{g.name}</Title>
            <LeagueTable rows={g.rows} phone={phone} userId={career?.club.id} mark={mark} />
          </Stack>
        ))
      ) : (
        <LeagueTable rows={rows} phone={phone} userId={career?.club.id} mark={mark} />
      )}
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
                    {playoff ? ` ${p.round_name?.toLowerCase() ?? 'qualifying'}` : ''}
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
      {brackets.map((p) => (
        <Playoff key={p.key} playoff={p} userId={career?.club.id} />
      ))}
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

type Mark = (r: TableRow) => { bg: string | undefined; stripe: string | undefined; title: string | undefined }

function LeagueTable({ rows, phone, userId, mark }: { rows: TableRow[]; phone: boolean; userId: number | undefined; mark: Mark }) {
  return (
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
            <Table.Tr key={r.club.id} bg={mark(r).bg} fw={r.club.id === userId ? 700 : undefined}>
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
  )
}

/** A league's play-off: its drawn rounds as cards, the rounds to come by date. */
function Playoff({ playoff, userId }: { playoff: LeaguePlayoff; userId: number | undefined }) {
  const drawn = playoff.rounds.filter((r) => r.drawn)
  const toCome = playoff.rounds.filter((r) => !r.drawn)
  return (
    <Stack gap="xs">
      <Group justify="space-between">
        <Title order={3}>{playoff.name}</Title>
        {playoff.winner && (
          <Badge variant="light" color="yellow" size="lg" tt="none">
            Winners: {playoff.winner.name}
          </Badge>
        )}
      </Group>
      {drawn.map((round) => (
        <RoundCard key={round.index} round={round} userId={userId} series={(round.games ?? 1) > 1 ? round.games : undefined} />
      ))}
      {toCome.length > 0 && (
        <Card withBorder padding="sm">
          <Text size="sm" fw={600} mb={4}>
            {drawn.length ? 'Still to come' : 'After the regular season'}
          </Text>
          {toCome.map((r) => (
            <Text key={r.index} size="sm" c="dimmed">
              {r.name} · {r.dates.map(longDate).join(', ')}
            </Text>
          ))}
        </Card>
      )}
    </Stack>
  )
}
