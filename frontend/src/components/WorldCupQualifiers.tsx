import { Badge, Button, Card, Group, SegmentedControl, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core'
import { Link } from '@tanstack/react-router'
import { useState } from 'react'

import { useCupHistory, useQualifiers, useWorldCupFinals } from '../api/hooks'
import type { QualifierStage, WorldCupFinals } from '../api/types'
import ClubLink from './ClubLink'
import PastFinals from './PastFinals'

const REGIONS = [
  { value: 'UEFA', label: 'UEFA' },
  { value: 'CONMEBOL', label: 'CONMEBOL' },
  { value: 'CONCACAF', label: 'CONCACAF' },
  { value: 'AFC', label: 'AFC' },
  { value: 'CAF', label: 'CAF' },
  { value: 'OFC', label: 'OFC' },
  { value: 'FIFA', label: 'Play-off' },
]

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const month = (ym: string) => `${MONTHS[Number(ym.slice(5, 7)) - 1]} ${ym.slice(0, 4)}`

/** The World Cup qualifiers: who is through so far, then each confederation's stages, their
 * group tables and play-off ties. */
export default function WorldCupQualifiers() {
  const data = useQualifiers().data
  const finals = useWorldCupFinals().data
  const history = useCupHistory().data
  const [region, setRegion] = useState('UEFA')
  // A past World Cup picked from the history, shown instead of the current one.
  const [past, setPast] = useState<number | null>(null)
  if (!data) return null
  const pastFinals = <PastFinals title="Past World Cups" finals={history?.world_cup ?? []} onView={setPast} />
  if (past !== null) {
    return (
      <Stack>
        <Group>
          <Button size="xs" variant="default" onClick={() => setPast(null)}>
            ← Back to the {finals && finals.groups.length > 0 ? finals.year : data.cycle} World Cup
          </Button>
        </Group>
        <PastWorldCup year={past} />
        {pastFinals}
      </Stack>
    )
  }
  if (finals && finals.groups.length > 0) {
    return (
      <Stack>
        <Finals data={finals} />
        {pastFinals}
      </Stack>
    )
  }
  const stages = data.stages.filter((s) => s.confederation === region)
  return (
    <Stack>
      <Card withBorder padding="sm" aria-label="Qualified">
        <Group justify="space-between" mb={4}>
          <Title order={4}>World Cup {data.cycle}: qualified</Title>
          <Badge variant="light">{data.qualified.length} / 48</Badge>
        </Group>
        <Group gap={6}>
          {data.qualified.map((q) => (
            <Badge key={q.team.id} variant="light" color={q.how === 'Hosts' ? 'yellow' : 'teal'} tt="none" title={q.how}>
              {q.team.name}
            </Badge>
          ))}
        </Group>
      </Card>
      <SegmentedControl value={region} onChange={setRegion} data={REGIONS} aria-label="Confederation" />
      {stages.map((s) => (
        <StageCard key={s.key} stage={s} />
      ))}
      {pastFinals}
    </Stack>
  )
}

function PastWorldCup({ year }: { year: number }) {
  const finals = useWorldCupFinals(year)
  if (finals.isPending) return null
  if (!finals.data) return <Text c="red">{finals.error?.message}</Text>
  return <Finals data={finals.data} />
}

function StageCard({ stage }: { stage: QualifierStage }) {
  return (
    <Card withBorder padding="sm" aria-label={stage.name}>
      <Group justify="space-between" mb="xs">
        <Title order={4}>{stage.name}</Title>
        <Text size="sm" c="dimmed">
          From {month(stage.starts)}
        </Text>
      </Group>
      {!stage.drawn && (
        <Text size="sm" c="dimmed">
          Drawn the day before the {month(stage.starts)} window.
        </Text>
      )}
      {stage.groups.length > 0 && (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="sm">
          {stage.groups.map((g) => (
            <div key={g.name}>
              <Text fw={600} size="sm" mb={2}>
                {g.name}
              </Text>
              <Table withRowBorders={false} verticalSpacing={2}>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th />
                    <Table.Th ta="right">P</Table.Th>
                    <Table.Th ta="right">GD</Table.Th>
                    <Table.Th ta="right">Pts</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {g.rows.map((r, i) => (
                    <Table.Tr key={r.team.id} bg={stage.qualified_ranks?.includes(i + 1) ? 'var(--mantine-color-teal-light)' : undefined}>
                      <Table.Td>
                        <Text size="sm" truncate>
                          <ClubLink club={r.team} />
                        </Text>
                      </Table.Td>
                      <Table.Td ta="right" className="fs-num">
                        {r.played}
                      </Table.Td>
                      <Table.Td ta="right" className="fs-num">
                        {r.gd > 0 ? `+${r.gd}` : r.gd}
                      </Table.Td>
                      <Table.Td ta="right" className="fs-num" fw={600}>
                        {r.points}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </div>
          ))}
        </SimpleGrid>
      )}
      {stage.ties.length > 0 && (
        <Stack gap={6}>
          {stage.ties.map((t) => (
            <div key={t.tie}>
              <Text size="xs" c="dimmed">
                {t.name}
              </Text>
              {t.fixtures.map((f) => (
                <Group key={f.id} justify="space-between" wrap="nowrap" className="fs-row">
                  <Text size="sm" truncate>
                    <ClubLink club={f.home} /> v <ClubLink club={f.away} />
                  </Text>
                  {f.status === 'played' ? (
                    <Link to="/match/$fixtureId" params={{ fixtureId: String(f.id) }}>
                      <Text className="fs-num" fw={600}>
                        {f.home_goals}–{f.away_goals}
                        {f.home_pens !== null ? ` (${f.home_pens}–${f.away_pens} pens)` : ''}
                      </Text>
                    </Link>
                  ) : (
                    <Text size="sm" c="dimmed">
                      {f.date}
                    </Text>
                  )}
                </Group>
              ))}
            </div>
          ))}
        </Stack>
      )}
    </Card>
  )
}

/** The finals, once drawn: the champion, the knockout rounds (latest first) and the groups. */
function Finals({ data }: { data: WorldCupFinals }) {
  return (
    <Stack>
      {data.champion && (
        <Card withBorder padding="sm" className="fs-hero">
          <Title order={3}>
            {data.champion.name}, {data.year} world champions
          </Title>
        </Card>
      )}
      {[...data.rounds].reverse().map((r) => (
        <Card key={r.name} withBorder padding="sm">
          <Title order={5} mb={4}>
            {r.name}
          </Title>
          {r.fixtures.map((f) => (
            <Group key={f.id} justify="space-between" wrap="nowrap" className="fs-row">
              <Text size="sm" truncate>
                <ClubLink club={f.home} /> v <ClubLink club={f.away} />
              </Text>
              {f.status === 'played' ? (
                <Link to="/match/$fixtureId" params={{ fixtureId: String(f.id) }}>
                  <Text className="fs-num" fw={600}>
                    {f.home_goals}–{f.away_goals}
                    {f.home_pens !== null ? ` (${f.home_pens}–${f.away_pens} pens)` : ''}
                  </Text>
                </Link>
              ) : (
                <Text size="sm" c="dimmed">
                  {f.date}
                </Text>
              )}
            </Group>
          ))}
        </Card>
      ))}
      <StageCard
        stage={{ key: 'WCF', name: `World Cup ${data.year}: groups`, confederation: 'FIFA', starts: data.draw.slice(0, 7), drawn: true, qualified_ranks: [1, 2], groups: data.groups, ties: [] }}
      />
    </Stack>
  )
}
