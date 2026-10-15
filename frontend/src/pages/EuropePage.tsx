import type { ReactNode } from 'react'
import { Accordion, Card, Group, Loader, SegmentedControl, Select, SimpleGrid, Stack, Text, Title } from '@mantine/core'

import { useCareer, useEurope, useEuropeList, useSeasons } from '../api/hooks'
import type { Career, CupRound, Europe, EuropeSummary } from '../api/types'
import ClubLink from '../components/ClubLink'
import Entrants from '../components/europe/Entrants'
import Knockouts from '../components/europe/Knockouts'
import LeaguePhase from '../components/europe/LeaguePhase'
import Rankings from '../components/europe/Rankings'
import { dateList, PATH_ORDER } from '../components/europe/shared'
import TieCard from '../components/europe/TieCard'
import { useUrlState } from '../lib/urlState'

/** The competition to open on: the one the user's club is still in, else one it was in, else the
 * Champions League. */
function defaultKey(competitions: EuropeSummary[]): string | undefined {
  const mine = competitions.filter((c) => c.user_status)
  return (mine.find((c) => !c.user_status?.startsWith('Out')) ?? mine[0] ?? competitions[0])?.key
}

/** The Champions League, Europa League and Conference League: the league phase, the knockout
 * rounds, the summer qualifying rounds and the entrants, a season at a time. */
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
  const rankingsView = keyParam === 'rankings'
  const active = rankingsView
    ? undefined
    : (competitions.find((c) => c.key === keyParam)?.key ?? (past ? competitions[0]?.key : defaultKey(competitions)))
  const europe = useEurope(active, past ? Number(seasonId) : null)
  // What is under way and how the user's club is doing are about this season only.
  const summary = past ? undefined : competitions.find((c) => c.key === active)
  const data = europe.data
  const pickerData = [...competitions.map((c) => ({ value: c.key, label: c.short_name })), { value: 'rankings', label: 'Rankings' }]

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
          {rankingsView ? 'Europe: rankings' : (data?.name ?? 'Europe')}
          {data && !rankingsView && (
            <Text span c="dimmed" fz="lg" ml="xs">
              {data.season}
            </Text>
          )}
        </Title>
        <Group>
          {seasons.length > 1 && !rankingsView && (
            <Select
              aria-label="Season"
              w={150}
              value={seasonId ?? String(current?.id ?? '')}
              onChange={setSeasonId}
              allowDeselect={false}
              data={seasons.map((s) => ({ value: String(s.id), label: s.current ? `${s.label} (now)` : s.label }))}
            />
          )}
          {competitions.length > 0 && (
            <>
              <SegmentedControl aria-label="Competition" visibleFrom="sm" value={active ?? 'rankings'} onChange={setKey} data={pickerData} />
              <Select
                aria-label="Competition"
                hiddenFrom="sm"
                w={190}
                value={active ?? 'rankings'}
                onChange={(v) => v && setKey(v)}
                allowDeselect={false}
                data={pickerData}
              />
            </>
          )}
        </Group>
      </Group>

      {rankingsView && <Rankings userId={career?.club.id} userNation={career?.competition?.nation} />}
      {!rankingsView && (list.isPending || europe.isPending) && !data && <Loader size="sm" />}
      {!rankingsView && data && (
        <>
          <Facts data={data} summary={summary} clubName={career?.club.name} />
          <Body data={data} userId={career?.club.id} career={career} current={!past} />
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
  userId,
  career,
  current,
}: {
  data: Europe
  userId: number | undefined
  career: Career | undefined
  current: boolean
}) {
  const phase = data.league_phase
  const qualifying = data.qualifying
  const anyDrawn = qualifying.drawn || phase.drawn || data.knockout.some((r) => r.drawn)
  // Every qualifying round and path drawn, first round first, the paths grouped in each round (a
  // server that sends no list gets the latest round only).
  const rounds: CupRound[] = (data.qualifying_rounds ?? (qualifying.drawn ? [qualifying] : [])).filter((r) => r.drawn)
  const roundId = (r: CupRound, i: number) => `qualifying-${r.round ?? i}-${r.path ?? ''}`
  rounds.sort((a, b) => a.index - b.index || PATH_ORDER.indexOf(a.path ?? 'main') - PATH_ORDER.indexOf(b.path ?? 'main'))
  // Qualifying is what is happening until the league phase is drawn: the latest round is open.
  const latest = rounds.length ? Math.max(...rounds.map((r) => r.index)) : null
  const open = [
    ...(!phase.drawn ? rounds.filter((r) => r.index === latest).map(roundId) : []),
    ...(!anyDrawn ? ['entrants'] : []),
  ]

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
            <Knockouts rounds={data.knockout} phase={phase} userId={userId} career={career} />
          </Card>
        </>
      )}
      {(rounds.length > 0 || data.entries.length > 0) && (
        <Accordion
          multiple
          variant="separated"
          key={`${data.key}-${data.season}-${latest}-${phase.drawn}-${data.entries.length === 0}`}
          defaultValue={open}
        >
          {rounds.map((r, i) => (
            <Accordion.Item key={roundId(r, i)} value={roundId(r, i)}>
              <Accordion.Control>
                Qualifying: {r.name.toLowerCase()}{' '}
                <Text span size="sm" c="dimmed">
                  ({r.ties.length} {r.ties.length === 1 ? 'tie' : 'ties'})
                </Text>
              </Accordion.Control>
              <Accordion.Panel>
                <Text size="sm" c="dimmed" mb="xs">
                  {r.legs > 1 ? 'Two legs' : 'One match'} in the summer ({dateList(r.dates)}).{' '}
                  {roundNote(r, data)}
                </Text>
                <SimpleGrid cols={{ base: 1, xs: 2, md: 3, lg: 4 }} spacing="xs">
                  {r.ties.map((t) => (
                    <TieCard key={t.tie} tie={t} legs={r.legs} userId={userId} career={career} />
                  ))}
                </SimpleGrid>
              </Accordion.Panel>
            </Accordion.Item>
          ))}
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

/** The span of the qualifying rounds: first round's first date to last round's last date. */
function rangeText(data: Europe): string {
  const rounds = data.qualifying_rounds?.length ? data.qualifying_rounds : [data.qualifying]
  const dates = rounds.flatMap((r) => r.dates).sort()
  return dates.length ? `${dateList([dates[0]!])} to ${dateList([dates[dates.length - 1]!])}` : ''
}

/** Where a qualifying round's winners and losers go, in a sentence. */
function roundNote(r: CupRound, data: Europe): string {
  const losers =
    data.key === 'UECL'
      ? 'the losers are out'
      : `the losers can drop into the ${data.key === 'UCL' ? 'Europa League' : 'Conference League'}`
  return r.round === 'PO' ? `The winners go into the league phase; ${losers}.` : `The winners go through to the next round; ${losers}.`
}

/** Before anything is drawn: when the competition starts and its dates. */
function Coming({ data, current }: { data: Europe; current: boolean }) {
  const phase = data.league_phase
  const first = phase.matchdays[0]?.dates[0]
  const last = phase.matchdays[phase.matchdays.length - 1]?.dates.slice(-1)[0]
  const rows: [string, string][] = [
    ['Qualifying rounds', rangeText(data)],
    ['League phase', first && last ? `${phase.matches} matches each, ${dateList([first])} to ${dateList([last])}` : `${phase.matches} matches each`],
    ...data.knockout.map((r): [string, string] => [r.name, dateList(r.dates)]),
  ]
  return (
    <Card withBorder padding="md">
      <Title order={4}>{current ? 'Not under way yet' : 'Not played'}</Title>
      <Text size="sm" c="dimmed" mt={4} mb="sm">
        {current
          ? `The ${data.name} starts with the summer qualifying rounds (July and August). The league phase is drawn once they are over, the knockout rounds follow.`
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
