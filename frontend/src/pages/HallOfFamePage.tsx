import { Alert, Badge, Card, Group, Loader, SegmentedControl, SimpleGrid, Stack, Table, Text, Title, UnstyledButton } from '@mantine/core'
import { Link } from '@tanstack/react-router'
import { useMemo, useState } from 'react'

import { type FormerPlayer, useHallOfFame } from '../api/hallOfFame'
import ClubLink from '../components/ClubLink'
import { useDevice } from '../lib/device'
import { matchRatingColor, positionColor } from '../lib/format'

// The Hall of fame (api/hall_of_fame.py): your club's greats, and everyone who has played for it
// in your career with their record there and where they are now.

type SortKey = 'appearances' | 'goals' | 'assists' | 'average_rating' | 'seasons' | 'last_season'

const COLUMNS: { key: SortKey; label: string; phone: boolean }[] = [
  { key: 'last_season', label: 'Years', phone: false },
  { key: 'appearances', label: 'Apps', phone: true },
  { key: 'goals', label: 'Goals', phone: true },
  { key: 'assists', label: 'Assists', phone: false },
  { key: 'average_rating', label: 'Rating', phone: true },
]

function nowText(p: FormerPlayer) {
  if (p.now === 'with_you') return 'With you'
  if (p.now === 'retired') return 'Retired'
  if (p.now === 'free_agent') return 'Free agent'
  return null
}

function Now({ p }: { p: FormerPlayer }) {
  const text = nowText(p)
  if (text) return <>{text}</>
  return p.club ? <ClubLink club={p.club} /> : null
}

function years(p: FormerPlayer) {
  return p.first_season === p.last_season ? p.first_season : `${p.first_season} – ${p.last_season}`
}

function PlayerName({ p }: { p: FormerPlayer }) {
  return (
    <Link to="/players/$playerId" params={{ playerId: String(p.player_id) }} style={{ color: 'inherit', fontWeight: 600 }}>
      {p.name}
    </Link>
  )
}

/** A Hall of famer's card. */
function Legend({ p }: { p: FormerPlayer }) {
  return (
    <Card withBorder padding="sm" bg="var(--mantine-color-yellow-light)">
      <Group gap="xs" wrap="nowrap">
        <Badge color={positionColor(p.position)} variant="light" w={44}>
          {p.position}
        </Badge>
        <Text fw={700} truncate>
          <PlayerName p={p} />
        </Text>
      </Group>
      <Text size="sm" mt={4}>
        {p.appearances} apps · {p.goals} goals · {p.assists} assists
        {p.average_rating !== null ? ` · ${p.average_rating.toFixed(2)} rating` : ''}
      </Text>
      <Text size="xs" c="dimmed">
        {years(p)} · now: <Now p={p} />
      </Text>
      {p.titles.length > 0 && (
        <Text size="xs" mt={4}>
          {p.titles.join(' · ')}
        </Text>
      )}
    </Card>
  )
}

export default function HallOfFamePage() {
  const { phone } = useDevice()
  const data = useHallOfFame()
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'appearances', desc: true })
  const [who, setWho] = useState('all')
  const rows = useMemo(() => {
    const list = (data.data?.players ?? []).filter((p) => who === 'all' || (who === 'current' ? p.now === 'with_you' : p.now !== 'with_you'))
    const value = (p: FormerPlayer) => (sort.key === 'last_season' ? p.last_season : sort.key === 'average_rating' ? (p.average_rating ?? 0) : p[sort.key])
    return [...list].sort((a, b) => {
      const x = value(a)
      const y = value(b)
      const c = typeof x === 'string' ? x.localeCompare(String(y)) : x - (y as number)
      return sort.desc ? -c : c
    })
  }, [data.data, sort, who])

  if (data.isPending) return <Loader />
  if (data.error) return <Alert color="red">{data.error.message}</Alert>
  const h = data.data
  const legends = h.players.filter((p) => p.hall_of_fame)

  return (
    <Stack gap="sm">
      <div>
        <Title order={2}>Hall of fame</Title>
        <Text size="sm" c="dimmed">
          {h.club.name}: everyone who has played for you, and the greats.
        </Text>
      </div>
      <Card withBorder padding="md">
        <Text fw={700}>The greats</Text>
        <Text size="xs" c="dimmed" mb="xs">
          To get in: {h.rule}.
        </Text>
        {legends.length === 0 ? (
          <Text size="sm" c="dimmed">
            Nobody yet.
          </Text>
        ) : (
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing="xs">
            {legends.map((p) => (
              <Legend key={p.player_id} p={p} />
            ))}
          </SimpleGrid>
        )}
      </Card>
      <Group justify="space-between" align="center">
        <Title order={3}>Everyone who has played for you</Title>
        <SegmentedControl size="xs" value={who} onChange={setWho} data={[{ value: 'all', label: 'All' }, { value: 'current', label: 'Current' }, { value: 'former', label: 'Former' }]} />
      </Group>
      {rows.length === 0 ? (
        <Text size="sm" c="dimmed">
          Nobody has played a match for you yet.
        </Text>
      ) : (
        <Table.ScrollContainer minWidth={phone ? 0 : 720}>
          <Table striped highlightOnHover verticalSpacing={4}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Player</Table.Th>
                {COLUMNS.map((c) => (
                  <Table.Th key={c.key} ta={c.key === 'last_season' ? undefined : 'right'} visibleFrom={c.phone ? undefined : 'sm'}>
                    <UnstyledButton fw={600} fz="sm" onClick={() => setSort((s) => ({ key: c.key, desc: s.key === c.key ? !s.desc : true }))}>
                      {c.label}
                      {sort.key === c.key ? (sort.desc ? ' ▾' : ' ▴') : ''}
                    </UnstyledButton>
                  </Table.Th>
                ))}
                <Table.Th visibleFrom="sm">Now</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((p) => (
                <Table.Tr key={p.player_id}>
                  <Table.Td>
                    <Group gap={6} wrap="nowrap">
                      <Badge color={positionColor(p.position)} variant="light" w={44} style={{ flexShrink: 0 }}>
                        {p.position}
                      </Badge>
                      <div style={{ minWidth: 0 }}>
                        <Text size="sm" truncate>
                          <PlayerName p={p} />
                          {p.hall_of_fame && (
                            <Badge ml={6} size="xs" color="yellow" variant="filled">
                              Hall of fame
                            </Badge>
                          )}
                        </Text>
                        <Text size="xs" c="dimmed" hiddenFrom="sm">
                          {years(p)} · <Now p={p} />
                        </Text>
                      </div>
                    </Group>
                  </Table.Td>
                  <Table.Td visibleFrom="sm">
                    <Text size="sm">{years(p)}</Text>
                  </Table.Td>
                  <Table.Td ta="right">{p.appearances}</Table.Td>
                  <Table.Td ta="right">{p.goals}</Table.Td>
                  <Table.Td ta="right" visibleFrom="sm">
                    {p.assists}
                  </Table.Td>
                  <Table.Td ta="right">
                    {p.average_rating !== null && (
                      <Text size="sm" fw={600} c={matchRatingColor(p.average_rating)} span>
                        {p.average_rating.toFixed(2)}
                      </Text>
                    )}
                  </Table.Td>
                  <Table.Td visibleFrom="sm">
                    <Text size="sm">
                      <Now p={p} />
                    </Text>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </Stack>
  )
}
