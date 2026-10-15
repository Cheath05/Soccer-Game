import { Badge, Card, Group, SimpleGrid, Text, Title } from '@mantine/core'

import type { EuropeEntry } from '../../api/types'
import ClubLink from '../ClubLink'
import { PATH_ORDER, ROUND_ORDER, roundTitle } from './shared'

interface Group_ {
  id: string
  title: string
  entries: EuropeEntry[]
}

/** The entrants in groups: a pot at a time once the league phase is drawn, then those in the league
 * phase without a pot yet (waiting for the draw), then those still in each qualifying round and
 * path (first round first), and last those knocked out in qualifying. */
function groups(entries: EuropeEntry[]): Group_[] {
  const out: Group_[] = []
  const pots = [...new Set(entries.filter((e) => e.stage === 'league_phase' && e.pot !== null).map((e) => e.pot as number))].sort((a, b) => a - b)
  for (const pot of pots) out.push({ id: `pot-${pot}`, title: `Pot ${pot}`, entries: entries.filter((e) => e.stage === 'league_phase' && e.pot === pot) })
  const waiting = entries.filter((e) => e.stage === 'league_phase' && e.pot === null)
  if (waiting.length) out.push({ id: 'waiting', title: pots.length ? 'League phase, no pot' : 'In the league phase, awaiting the draw', entries: waiting })
  const qualifying = entries.filter((e) => e.stage === 'qualifying')
  for (const round of ROUND_ORDER) {
    for (const path of [...PATH_ORDER, null]) {
      const here = qualifying.filter((e) => e.round === round && (e.path ?? null) === path)
      if (here.length) out.push({ id: `q-${round}-${path}`, title: `In the ${roundTitle(round, path).replace(/^./, (c) => c.toLowerCase())}`, entries: here })
    }
  }
  // An entry from a server that sends no round still shows, in one group.
  const placed = new Set(out.flatMap((g) => g.entries.map((e) => e.club.id)))
  const rest = qualifying.filter((e) => !placed.has(e.club.id))
  if (rest.length) out.push({ id: 'qualifying', title: 'In qualifying', entries: rest })
  const gone = entries.filter((e) => e.stage === 'out')
  if (gone.length) out.push({ id: 'out', title: 'Out in qualifying', entries: gone })
  return out
}

/** Who is in the competition and how each club got its place, with its country. */
export default function Entrants({ entries, userId }: { entries: EuropeEntry[]; userId: number | undefined }) {
  if (entries.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        The entrants aren’t known yet.
      </Text>
    )
  }
  return (
    <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="sm">
      {groups(entries).map((g) => (
        <Card key={g.id} withBorder padding="xs" aria-label={g.title} style={g.entries.length > 12 ? { gridColumn: '1 / -1' } : undefined}>
          <Group justify="space-between" mb={4}>
            <Title order={6}>{g.title}</Title>
            <Text size="xs" c="dimmed">
              {g.entries.length} clubs
            </Text>
          </Group>
          <SimpleGrid cols={{ base: 1, sm: g.entries.length > 12 ? 2 : 1, lg: g.entries.length > 12 ? 3 : 1 }} spacing={4} verticalSpacing={6}>
            {g.entries.map((e) => (
              <Group key={e.club.id} gap="xs" wrap="nowrap" align="flex-start">
                <Badge size="xs" variant="light" color="gray" w={38} style={{ flexShrink: 0, marginTop: 3 }}>
                  {e.nation}
                </Badge>
                <div style={{ minWidth: 0 }}>
                  <Text size="sm" fw={e.club.id === userId ? 700 : undefined} lh={1.3}>
                    <ClubLink club={e.club} />
                  </Text>
                  <Text size="xs" c="dimmed" lh={1.3}>
                    {e.how}
                  </Text>
                  {e.came_from && (
                    <Text size="xs" c="dimmed" lh={1.3}>
                      {e.came_from}
                    </Text>
                  )}
                </div>
              </Group>
            ))}
          </SimpleGrid>
        </Card>
      ))}
    </SimpleGrid>
  )
}
