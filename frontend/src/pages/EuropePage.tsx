import type { ReactNode } from 'react'
import { Accordion, Card, Group, Loader, SegmentedControl, Select, SimpleGrid, Stack, Text, Title } from '@mantine/core'

import { useCareer, useEurope, useEuropeList, useSeasons } from '../api/hooks'
import type { Career, Europe, EuropeSummary } from '../api/types'
import ClubLink from '../components/ClubLink'
import Entrants from '../components/europe/Entrants'
import Knockouts from '../components/europe/Knockouts'
import LeaguePhase from '../components/europe/LeaguePhase'
import { dateList } from '../components/europe/shared'
import TieCard from '../components/europe/TieCard'
import { useUrlState } from '../lib/urlState'

/** The competition to open on: the one the user's club is still in, else one it was in, else the
 * Champions League. */
function defaultKey(competitions: EuropeSummary[]): string | undefined {
  const mine = competitions.filter((c) => c.user_status)
  return (mine.find((c) => !c.user_status?.startsWith('Out')) ?? mine[0] ?? competitions[0])?.key
}

/** The Champions League, Europa League and Conference League: the league phase, the knockout
 * rounds, the summer play-off round and the entrants, a season at a time. */
export default function EuropePage() {
  const career = useCareer().data
  const list = useEuropeList()
  const seasons = useSeasons().data ?? []
  const [keyParam, setKey] = useUrlState<string | null>('c', null)
  const [seasonIdRaw, setSeasonId] = useUrlState<string | null>('season', null)
  const seasonId = seasonIdRaw === null ? null : String(seasonIdRaw)
  const current = seasons.find((s) => s.current)
  const past = seasonId !== null && Number(seasonId) !== current?.id
  const competitions = list.data?.competitions ?? []
  const active = competitions.find((c) => c.key === keyParam)?.key ?? (past ? competitions[0]?.key : defaultKey(competitions))
  const europe = useEurope(active, past ? Number(seasonId) : null)
  // What is under way and how the user's club is doing are about this season only.
  const summary = past ? undefined : competitions.find((c) => c.key === active)
  const data = europe.data
  const pickerData = competitions.map((c) => ({ value: c.key, label: c.short_name }))

  if (list.data && !list.data.enabled) {
    return (
      <Stack>
        <Title order={2}>Europe</Title>
        <Text c="dimmed">This game has no European competitions.</Text>
      </Stack>
    )
  }

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>
          {data?.name ?? 'Europe'}
          {data && (
            <Text span c="dimmed" fz="lg" ml="xs">
              {data.season}
            </Text>
          )}
        </Title>
        <Group>
          {seasons.length > 1 && (
            <Select
              aria-label="Season"
              w={150}
              value={seasonId ?? String(current?.id ?? '')}
              onChange={setSeasonId}
              allowDeselect={false}
              data={seasons.map((s) => ({ value: String(s.id), label: s.current ? `${s.label} (now)` : s.label }))}
            />
          )}
          {competitions.length > 1 && active && (
            <>
              <SegmentedControl aria-label="Competition" visibleFrom="sm" value={active} onChange={setKey} data={pickerData} />
              <Select
                aria-label="Competition"
                hiddenFrom="sm"
                w={190}
                value={active}
                onChange={(v) => v && setKey(v)}
                allowDeselect={false}
                data={pickerData}
              />
            </>
          )}
        </Group>
      </Group>

      {(list.isPending || europe.isPending) && !data && <Loader size="sm" />}
      {data && (
        <>
          <Facts data={data} summary={summary} clubName={career?.club.name} />
          <Body data={data} competitions={competitions} userId={career?.club.id} career={career} current={!past} />
        </>
      )}
    </Stack>
  )
}

function Facts({ data, summary, clubName }: { data: Europe; summary: EuropeSummary | undefined; clubName: string | undefined }) {
  const facts: { label: string; value: ReactNode; gold?: boolean }[] = []
  if (summary?.stage && !data.winner) facts.push({ label: 'Now', value: summary.stage })
  if (summary?.user_status) facts.push({ label: clubName ?? 'Your club', value: summary.user_status })
  if (data.winner) facts.push({ label: 'Winners', value: <ClubLink club={data.winner} />, gold: true })
  if (facts.length === 0) return null
  return (
    <SimpleGrid cols={{ base: 1, sm: Math.min(facts.length, 3) }}>
      {facts.map((f) => (
        <Card
          key={f.label}
          withBorder
          padding="sm"
          bg={f.gold ? 'var(--mantine-color-yellow-light)' : undefined}
          style={f.gold ? { borderLeft: '4px solid var(--mantine-color-yellow-6)' } : undefined}
        >
          <Text size="xs" c="dimmed">
            {f.label}
          </Text>
          <Text fw={700}>{f.value}</Text>
        </Card>
      ))}
    </SimpleGrid>
  )
}

function Body({
  data,
  competitions,
  userId,
  career,
  current,
}: {
  data: Europe
  competitions: EuropeSummary[]
  userId: number | undefined
  career: Career | undefined
  current: boolean
}) {
  const phase = data.league_phase
  const qualifying = data.qualifying
  const anyDrawn = qualifying.drawn || phase.drawn || data.knockout.some((r) => r.drawn)
  const next = competitions[competitions.findIndex((c) => c.key === data.key) + 1]
  // Qualifying is what is happening until the league phase is drawn; the entrants are the news
  // before anything is.
  const open = [...(!phase.drawn && qualifying.drawn ? ['qualifying'] : []), ...(!anyDrawn ? ['entrants'] : [])]

  return (
    <Stack>
      {!anyDrawn && <Coming data={data} current={current} />}
      {anyDrawn && (
        <>
          <LeaguePhase key={`${data.key}-${data.season}`} phase={phase} qualifyingDrawn={qualifying.drawn} userId={userId} career={career} />
          <Card withBorder padding="sm">
            <Title order={4} mb="xs">
              Knockout rounds
            </Title>
            <Knockouts rounds={data.knockout} userId={userId} career={career} />
          </Card>
        </>
      )}
      {(qualifying.drawn || data.entries.length > 0) && (
        <Accordion
          multiple
          variant="separated"
          key={`${data.key}-${data.season}-${qualifying.drawn}-${phase.drawn}-${data.entries.length === 0}`}
          defaultValue={open}
        >
          {qualifying.drawn && (
            <Accordion.Item value="qualifying">
              <Accordion.Control>Qualifying: {qualifying.name.toLowerCase()}</Accordion.Control>
              <Accordion.Panel>
                <Text size="sm" c="dimmed" mb="xs">
                  Two legs in the summer ({dateList(qualifying.dates)}). The winners go into the league phase
                  {next ? `; the losers drop into the ${next.short_name}.` : '; the losers are out.'}
                </Text>
                <SimpleGrid cols={{ base: 1, xs: 2, md: 3, lg: 4 }} spacing="xs">
                  {qualifying.ties.map((t) => (
                    <TieCard key={t.tie} tie={t} legs={qualifying.legs} userId={userId} career={career} />
                  ))}
                </SimpleGrid>
              </Accordion.Panel>
            </Accordion.Item>
          )}
          {data.entries.length > 0 && (
            <Accordion.Item value="entrants">
              <Accordion.Control>
                Entrants{' '}
                <Text span size="sm" c="dimmed">
                  ({data.entries.length})
                </Text>
              </Accordion.Control>
              <Accordion.Panel>
                <Entrants entries={data.entries} userId={userId} />
              </Accordion.Panel>
            </Accordion.Item>
          )}
        </Accordion>
      )}
    </Stack>
  )
}

/** Before anything is drawn: when the competition starts and its dates. */
function Coming({ data, current }: { data: Europe; current: boolean }) {
  const phase = data.league_phase
  const first = phase.matchdays[0]?.dates[0]
  const last = phase.matchdays[phase.matchdays.length - 1]?.dates.slice(-1)[0]
  const rows: [string, string][] = [
    [data.qualifying.name, dateList(data.qualifying.dates)],
    ['League phase', first && last ? `${phase.matches} matches each, ${dateList([first])} to ${dateList([last])}` : `${phase.matches} matches each`],
    ...data.knockout.map((r): [string, string] => [r.name, dateList(r.dates)]),
  ]
  return (
    <Card withBorder padding="md">
      <Title order={4}>{current ? 'Not under way yet' : 'Not played'}</Title>
      <Text size="sm" c="dimmed" mt={4} mb="sm">
        {current
          ? `The ${data.name} starts with the summer play-off round. The league phase is drawn once that is over, the knockout rounds follow.`
          : `The ${data.name} wasn’t played in ${data.season}.`}
      </Text>
      {current && (
        <Stack gap={2}>
          {rows.map(([label, dates]) => (
            <Group key={label} gap="sm" wrap="nowrap" align="baseline">
              <Text size="sm" fw={600} w={150} style={{ flexShrink: 0 }}>
                {label}
              </Text>
              <Text size="sm" c="dimmed">
                {dates}
              </Text>
            </Group>
          ))}
        </Stack>
      )}
    </Card>
  )
}
