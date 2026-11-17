import { Card, Group, SegmentedControl, Select, SimpleGrid, Stack, Text, Title } from '@mantine/core'

import { useCareer, useCup, useCups, useNations, useSeasons } from '../api/hooks'
import RoundCard from '../components/RoundCard'
import NationPicker from '../components/NationPicker'
import { competitionNation, groupByNation, longDate } from '../lib/format'
import { useUrlState } from '../lib/urlState'

// A cup's country: a server that predates the field only had England's cups.
const cupNation = (c: { nation?: string }) => c.nation ?? 'ENG'

/** The season's cups, a country's at a time (the user's own to start with): every round, drawn or
 * still to come, with its ties and results. */
export default function CupsPage() {
  const career = useCareer().data
  const allCups = useCups().data ?? []
  const seasons = useSeasons().data ?? []
  const [nationCode, setNationCode] = useUrlState<string | null>('nation', null)
  const [key, setKey] = useUrlState<string | null>('cup', null)
  const [seasonIdRaw, setSeasonId] = useUrlState<string | null>('season', null)
  const seasonId = seasonIdRaw === null ? null : String(seasonIdRaw)
  // The countries with cups (in the server's order: UEFA's ranking first), and the one shown: the
  // one picked, or the user's club's if it has cups, or else the first.
  const nations = groupByNation(allCups.map((c) => ({ key: c.key, name: c.name, tier: 1, nation: cupNation(c) })), useNations().data)
  const home = career?.competition ? competitionNation(career.competition) : undefined
  const nation = nationCode ?? (nations.some((n) => n.code === home) ? home : nations[0]?.code)
  const cups = allCups.filter((c) => cupNation(c) === nation)
  const active = cups.find((c) => c.key === key)?.key ?? cups[0]?.key
  const cupData = cups.map((c) => ({ value: c.key, label: c.name }))
  const pickNation = (code: string) => {
    setNationCode(code)
    setKey(null)
  }
  const cup = useCup(active, seasonId ? Number(seasonId) : null).data
  const summary = cups.find((c) => c.key === active)
  const userId = career?.club.id
  // Latest first: the round being played, then those before it; rounds still to come last.
  const drawn = (cup?.rounds ?? []).filter((r) => r.drawn).reverse()
  const toCome = (cup?.rounds ?? []).filter((r) => !r.drawn)

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>
          {cup?.name ?? 'Cups'}
          {cup && seasons.length > 1 && (
            <Text span c="dimmed" fz="lg" ml="xs">
              {cup.season}
            </Text>
          )}
        </Title>
        {seasons.length > 1 && (
          <Select
            aria-label="Season"
            w={130}
            value={seasonId ?? String(seasons.find((s) => s.current)?.id ?? '')}
            onChange={setSeasonId}
            allowDeselect={false}
            data={seasons.map((s) => ({ value: String(s.id), label: s.current ? `${s.label} (now)` : s.label }))}
          />
        )}
      </Group>
      {(nations.length > 1 || cups.length > 1) && (
        <Stack gap="xs">
          {nation && <NationPicker nations={nations} value={nation} onChange={pickNation} home={home} />}
          {cups.length > 1 && (
            <Group>
              <SegmentedControl aria-label="Cup" visibleFrom="sm" value={active ?? ''} onChange={setKey} data={cupData} />
              <Select aria-label="Cup" hiddenFrom="sm" w="100%" value={active ?? ''} onChange={(value) => value && setKey(value)} allowDeselect={false} data={cupData} />
            </Group>
          )}
        </Stack>
      )}

      {cup && (
        <SimpleGrid cols={{ base: 1, sm: 3 }}>
          <Fact label="Winners" value={cup.winner?.name ?? '–'} />
          {!seasonId && summary && <Fact label="Now" value={summary.current_round ?? (summary.winner ? 'Finished' : 'Not started')} />}
          {!seasonId && summary?.user_status && <Fact label={career?.club.name ?? 'You'} value={summary.user_status} />}
        </SimpleGrid>
      )}

      {cup && drawn.length === 0 && (
        <Text c="dimmed">
          {summary?.user_status === 'Starts next season'
            ? 'This career began before this cup was in the game: it starts with next season.'
            : 'The first round hasn’t been drawn yet.'}
        </Text>
      )}
      {drawn.map((round) => (
        <RoundCard key={round.index} round={round} userId={userId} />
      ))}
      {toCome.length > 0 && drawn.length > 0 && (
        <Card withBorder padding="sm">
          <Text fw={600} mb={4}>
            Still to come
          </Text>
          {toCome.map((r) => (
            <Text key={r.index} size="sm" c="dimmed">
              {r.name} · {r.dates.map(longDate).join(' and ')}
            </Text>
          ))}
        </Card>
      )}
    </Stack>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <Card withBorder padding="sm">
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text fw={700}>{value}</Text>
    </Card>
  )
}
