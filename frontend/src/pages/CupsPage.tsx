import { Badge, Card, Group, SegmentedControl, Select, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import { useCareer, useCup, useCups, useSeasons } from '../api/hooks'
import type { CupRound, CupTie } from '../api/types'
import ClubLink from '../components/ClubLink'
import { longDate, score } from '../lib/format'

/** The season's cups: every round, drawn or still to come, with its ties and results. */
export default function CupsPage() {
  const career = useCareer().data
  const cups = useCups().data ?? []
  const seasons = useSeasons().data ?? []
  const [key, setKey] = useState<string | null>(null)
  const [seasonId, setSeasonId] = useState<string | null>(null)
  const active = key ?? cups[0]?.key
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
        <Group>
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
          {cups.length > 0 && <SegmentedControl value={active ?? ''} onChange={setKey} data={cups.map((c) => ({ value: c.key, label: c.name }))} />}
        </Group>
      </Group>

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
            ? 'This career began before cups were in the game: they start with next season.'
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

function RoundCard({ round, userId }: { round: CupRound; userId: number | undefined }) {
  const navigate = useNavigate()
  const ties = round.ties.filter((t) => t.away)
  const exempt = round.ties.filter((t) => !t.away)
  return (
    <Card withBorder padding="sm" aria-label={round.name}>
      <Group justify="space-between" mb={4}>
        <Title order={4}>{round.name}</Title>
        <Text size="sm" c="dimmed">
          {round.dates.map(longDate).join(' and ')}
          {round.legs === 2 ? ' · two legs' : ''}
        </Text>
      </Group>
      <Table.ScrollContainer minWidth={520}>
        <Table highlightOnHover>
          <Table.Tbody>
            {ties.map((t) => {
              const mine = userId !== undefined && (t.home.id === userId || t.away?.id === userId)
              const played = t.fixtures.filter((f) => f.status === 'played')
              return (
                <Table.Tr
                  key={t.tie}
                  fw={mine ? 700 : undefined}
                  bg={mine ? 'var(--mantine-primary-color-light)' : undefined}
                  style={{ cursor: played.length ? 'pointer' : undefined }}
                  onClick={() => played.length && void navigate({ to: '/match/$fixtureId', params: { fixtureId: String(played[played.length - 1]!.id) } })}
                >
                  <Table.Td ta="right" w="40%">
                    <Side tie={t} side="home" />
                  </Table.Td>
                  <Table.Td ta="center" style={{ whiteSpace: 'nowrap' }}>
                    {played.length === 0 ? 'v' : t.fixtures.map((f) => (f.status === 'played' ? score(f) : 'v')).join(' · ')}
                  </Table.Td>
                  <Table.Td w="40%">
                    <Side tie={t} side="away" />
                  </Table.Td>
                </Table.Tr>
              )
            })}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {exempt.length > 0 && (
        <Text size="xs" c="dimmed" mt={4}>
          Exempt (no non-league clubs in the game yet): {exempt.map((t) => t.home.name).join(', ')}
        </Text>
      )}
    </Card>
  )
}

function Side({ tie, side }: { tie: CupTie; side: 'home' | 'away' }) {
  const club = side === 'home' ? tie.home : tie.away
  if (!club) return null
  const won = tie.winner?.id === club.id
  const lost = tie.winner !== null && !won
  return (
    <Group gap={6} wrap="nowrap" justify={side === 'home' ? 'flex-end' : 'flex-start'}>
      {side === 'away' && won && (
        <Badge size="xs" color="teal" variant="light">
          Through
        </Badge>
      )}
      <Text size="sm" fw={won ? 700 : undefined} c={lost ? 'dimmed' : undefined} component="span">
        <ClubLink club={club} />
      </Text>
      {side === 'home' && won && (
        <Badge size="xs" color="teal" variant="light">
          Through
        </Badge>
      )}
    </Group>
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
