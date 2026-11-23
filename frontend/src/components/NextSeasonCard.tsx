import { Badge, Card, Group, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import { Link } from '@tanstack/react-router'

import { type NextSeason, type OutlookPlayer, useNextSeason } from '../api/americas'
import { positionColor } from '../lib/format'

// A college coach's next season (api/college.py /next-season): by line, who stays (a class on),
// who leaves (graduating seniors, players who declared for the draft, and those likely to
// declare early), and who joins (signed and committed recruits, portal transfers included).

const STARS = (n: number) => '★'.repeat(n)

function Player({ p, leaving }: { p: OutlookPlayer; leaving?: boolean }) {
  return (
    <Group gap={6} wrap="nowrap">
      <Badge color={positionColor(p.position)} variant="light" w={40} size="sm" style={{ flexShrink: 0 }}>
        {p.position}
      </Badge>
      <Text size="sm" truncate style={{ flex: 1, minWidth: 0 }}>
        <Link to="/players/$playerId" params={{ playerId: String(p.id) }} style={{ color: 'inherit' }}>
          {p.name}
        </Link>{' '}
        <Text span size="xs" c="dimmed">
          {p.class_year} · {p.overall}
        </Text>
      </Text>
      {p.note && (
        <Badge size="xs" variant="light" color={leaving ? (p.note === 'graduating' ? 'gray' : 'orange') : p.note === 'agreed to stay' ? 'teal' : 'yellow'} style={{ flexShrink: 0 }}>
          {p.note === 'likely to declare early' ? 'may leave early' : p.note === 'declared for the draft' ? 'declared' : p.note === 'draft watch: may declare early' ? 'draft watch' : p.note}
        </Badge>
      )}
    </Group>
  )
}

export function NextSeasonSummary({ data }: { data: NextSeason }) {
  const total = data.staying + data.joining
  return (
    <Group gap="lg">
      <Text size="sm">
        <b>{data.staying}</b> staying
      </Text>
      <Text size="sm">
        <b>{data.leaving}</b> leaving{data.may_leave > 0 ? ` (${data.may_leave} may leave early)` : ''}
      </Text>
      <Text size="sm">
        <b>{data.joining}</b> joining
      </Text>
      <Text size="sm" c={total > data.roster_max ? 'red' : 'dimmed'}>
        {total} of {data.roster_max} places
      </Text>
    </Group>
  )
}

export default function NextSeasonCard() {
  const next = useNextSeason(true)
  if (!next.data) return next.error ? <Text c="red">{next.error.message}</Text> : null
  const d = next.data
  return (
    <Stack gap="sm">
      <Card withBorder padding="sm">
        <Title order={4}>Next season, {d.season}</Title>
        <Text size="xs" c="dimmed" mb={6}>
          Your squad after this season’s leavers and your incoming class. A player “may leave early” if he’d declare for the draft were it today (they declare after the College Cup): ask him to stay on his page. Joining: the recruits who have committed or signed (portal transfers included).
        </Text>
        <NextSeasonSummary data={d} />
      </Card>
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="sm">
        {d.lines.map((ln) => (
          <Card key={ln.line} withBorder padding="sm">
            <Group justify="space-between" mb={6}>
              <Text fw={700}>{ln.line}</Text>
              <Text size="xs" c="dimmed">
                {ln.staying.length + ln.joining.length} next season
              </Text>
            </Group>
            <Text size="xs" c="dimmed" fw={600} tt="uppercase">
              Joining ({ln.joining.length})
            </Text>
            <Stack gap={2} mb={6}>
              {ln.joining.length === 0 && (
                <Text size="xs" c="dimmed">
                  Nobody yet.
                </Text>
              )}
              {ln.joining.map((r) => (
                <Group key={r.id} gap={6} wrap="nowrap">
                  <Badge color={positionColor(r.position)} variant="light" w={40} size="sm" style={{ flexShrink: 0 }}>
                    {r.position}
                  </Badge>
                  <Text size="sm" truncate style={{ flex: 1, minWidth: 0 }}>
                    {r.name}{' '}
                    <Text span size="xs" c="yellow.6">
                      {STARS(r.stars)}
                    </Text>{' '}
                    <Text span size="xs" c="dimmed">
                      {r.overall_low}–{r.overall_high}
                      {r.portal_from ? ` · from ${r.portal_from}` : ''}
                    </Text>
                  </Text>
                  <Badge size="xs" variant={r.status === 'signed' ? 'filled' : 'light'} color="blue" style={{ flexShrink: 0 }}>
                    {r.status}
                  </Badge>
                </Group>
              ))}
            </Stack>
            <Text size="xs" c="dimmed" fw={600} tt="uppercase">
              Leaving ({ln.leaving.length})
            </Text>
            <Stack gap={2} mb={6}>
              {ln.leaving.length === 0 && (
                <Text size="xs" c="dimmed">
                  Nobody.
                </Text>
              )}
              {ln.leaving.map((p) => (
                <Player key={p.id} p={p} leaving />
              ))}
            </Stack>
            <Text size="xs" c="dimmed" fw={600} tt="uppercase">
              Staying ({ln.staying.length})
            </Text>
            <Stack gap={2}>
              {ln.staying.map((p) => (
                <Player key={p.id} p={p} />
              ))}
            </Stack>
          </Card>
        ))}
      </SimpleGrid>
    </Stack>
  )
}
