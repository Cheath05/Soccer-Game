import { Accordion, Badge, Group, List, Stack, Table, Text } from '@mantine/core'
import { Link } from '@tanstack/react-router'
import { useState } from 'react'
import type { MouseEvent, ReactNode } from 'react'

import type { ClubMove, Honour, SeasonFinal } from '../api/types'
import { longDate, nationName, ordinal, positionColor, ratingColor } from '../lib/format'
import ClubLink from './ClubLink'
import NationPicker from './NationPicker'
import Overall from './Overall'

const OUTCOME_TEXT: Record<string, string> = {
  champion: 'Champions',
  promoted: 'Promoted',
  playoff_winner: 'Promoted through the play-offs',
  playoffs: 'Play-offs',
  relegated: 'Relegated',
}

/** How the user's club finished: its place, record and cup runs. */
function Finish({ final }: { final: SeasonFinal }) {
  return (
    <Stack gap={2}>
      <Text fw={700}>
        {ordinal(final.position)} in the {final.competition}
        {final.outcome && OUTCOME_TEXT[final.outcome] ? ` · ${OUTCOME_TEXT[final.outcome]}` : ''}
      </Text>
      <Text size="sm" c="dimmed">
        Won {final.won}, drawn {final.drawn}, lost {final.lost} · goals {final.goals_for}–{final.goals_against} ·{' '}
        {final.points} points
      </Text>
      {(final.cups ?? []).map((run) => (
        <Text key={run.key} size="sm">
          {run.name}: {run.won ? 'Winners!' : run.reached === 'Final' ? 'Runners-up' : `out in the ${run.reached.toLowerCase()}`}
        </Text>
      ))}
    </Stack>
  )
}

function Section({ value, title, count, children }: { value: string; title: string; count?: number; children: ReactNode }) {
  return (
    <Accordion.Item value={value}>
      <Accordion.Control>
        <Group gap="xs">
          <Text fw={600}>{title}</Text>
          {count !== undefined && (
            <Badge size="sm" variant="light" color="gray">
              {count}
            </Badge>
          )}
        </Group>
      </Accordion.Control>
      <Accordion.Panel>{children}</Accordion.Panel>
    </Accordion.Item>
  )
}

function PlayerLink({ id, name }: { id: number; name: string }) {
  return (
    <Link
      to="/players/$playerId"
      params={{ playerId: String(id) }}
      style={{ color: 'inherit', fontWeight: 500, textDecoration: 'none' }}
      onMouseEnter={(e) => (e.currentTarget.style.textDecoration = 'underline')}
      onMouseLeave={(e) => (e.currentTarget.style.textDecoration = 'none')}
    >
      {name}
    </Link>
  )
}

function Position({ position }: { position: string }) {
  return (
    <Badge color={positionColor(position)} variant="light" w={44}>
      {position}
    </Badge>
  )
}

const KIND_ORDER = { league: 0, playoff: 1, cup: 2 } as const

function Champions({ honours }: { honours: Honour[] }) {
  if (honours.length === 0) return <Text size="sm" c="dimmed">No competitions here.</Text>
  const rows = [...honours].sort((a, b) => Number(a.kind === 'cup') - Number(b.kind === 'cup') || a.tier - b.tier || KIND_ORDER[a.kind] - KIND_ORDER[b.kind] || a.name.localeCompare(b.name))
  return (
    <Table verticalSpacing={4}>
      <Table.Tbody>
        {rows.map((h) => (
          <Table.Tr key={h.key}>
            <Table.Td>
              <Text size="sm">{h.name}</Text>
            </Table.Td>
            <Table.Td>
              <Text size="sm" fw={600}>
                <ClubLink club={h.winner} />
              </Text>
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  )
}

function Moves({ moves, userClubId, none }: { moves: ClubMove[]; userClubId: number; none: string }) {
  if (moves.length === 0) return <Text size="sm" c="dimmed">{none}</Text>
  return (
    <Table verticalSpacing={4}>
      <Table.Tbody>
        {moves.map((m) => (
          <Table.Tr key={m.club.id} fw={m.club.id === userClubId ? 700 : undefined}>
            <Table.Td>
              <ClubLink club={m.club} />
            </Table.Td>
            <Table.Td>
              <Text size="xs" c="dimmed">
                {m.position ? `${ordinal(m.position)} in the ${m.from_league}` : m.from_league}
              </Text>
            </Table.Td>
            <Table.Td>
              <Group gap="xs" wrap="nowrap">
                <Text size="sm">→ {m.to_league}</Text>
                {m.via_playoffs && (
                  <Badge size="xs" variant="light" color="teal">
                    Play-offs
                  </Badge>
                )}
              </Group>
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  )
}

/** The nations the summary has something to say about: England first, then by name. */
function nationsOf(final: SeasonFinal): { code: string; name: string }[] {
  const review = final.review
  if (!review) return []
  const codes = new Set([...review.honours, ...review.promoted, ...review.relegated].map((x) => x.nation).filter(Boolean))
  return [...codes]
    .map((code) => ({ code, name: nationName(code) }))
    .sort((a, b) => Number(a.code !== 'ENG') - Number(b.code !== 'ENG') || a.name.localeCompare(b.name))
}

/** The season's end as sections: the user's finish, then (one country at a time, the user's to
 * start with) the champions, promotions and relegations, and the user's squad: how its ratings
 * moved over the season, who retired, and the academy intake. `onNavigate` is called when a link
 * is followed, for the window holding the summary to close. */
export default function SeasonSummary({
  final,
  userClubId,
  userNation,
  onNavigate,
}: {
  final: SeasonFinal
  userClubId: number
  userNation?: string
  onNavigate: () => void
}) {
  const [picked, setPicked] = useState<string | null>(null)
  const review = final.review
  const nations = nationsOf(final)
  const nation = picked ?? (nations.some((n) => n.code === userNation) ? userNation : nations[0]?.code) ?? ''
  const country = nationName(nation)
  const news = final.news ?? []

  // Following a link from inside closes the window holding the summary.
  const closeOnLink = (e: MouseEvent<HTMLElement>) => {
    if ((e.target as HTMLElement).closest('a')) onNavigate()
  }

  return (
    <Stack gap="sm" onClickCapture={closeOnLink}>
      <Finish final={final} />
      {review && (
        <>
          <Group justify="space-between" wrap="wrap">
            <Text size="sm" c="dimmed">
              {review.next_season ? `The ${review.next_season} season begins.` : `The ${review.season} season is over.`}
            </Text>
            {nations.length > 1 && (
              <Group gap="xs">
                <Text size="sm" c="dimmed">
                  Country
                </Text>
                <NationPicker nations={nations} value={nation} onChange={setPicked} />
              </Group>
            )}
          </Group>
          <Accordion multiple variant="separated" defaultValue={['champions', 'development']}>
            <Section value="champions" title={`Champions${country ? ` · ${country}` : ''}`}>
              <Champions honours={review.honours.filter((h) => h.nation === nation)} />
            </Section>
            <Section value="promoted" title={`Promoted${country ? ` · ${country}` : ''}`}>
              <Moves moves={review.promoted.filter((m) => m.nation === nation)} userClubId={userClubId} none="No club went up." />
            </Section>
            <Section value="relegated" title={`Relegated${country ? ` · ${country}` : ''}`}>
              <Moves moves={review.relegated.filter((m) => m.nation === nation)} userClubId={userClubId} none="No club went down." />
            </Section>
            <Section value="development" title="Your squad's development" count={review.development.length}>
              <Stack gap="xs">
                {!review.development_recorded && (
                  <Text size="sm" c="dimmed">
                    The ratings at the start of this season weren&apos;t kept: it began before the game recorded them.
                  </Text>
                )}
                {review.development_recorded && review.development_since && (
                  <Text size="sm" c="dimmed">
                    The game began recording ratings on {longDate(review.development_since)}, part-way through the season: changes
                    are counted from then.
                  </Text>
                )}
                {review.development_recorded && review.development.length === 0 && (
                  <Text size="sm" c="dimmed">
                    No player&apos;s overall changed.
                  </Text>
                )}
                {review.development.length > 0 && (
                  <Table.ScrollContainer minWidth={380}>
                    <Table verticalSpacing={4}>
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>Pos</Table.Th>
                          <Table.Th>Player</Table.Th>
                          <Table.Th ta="right">Age</Table.Th>
                          <Table.Th ta="right">Start</Table.Th>
                          <Table.Th ta="right">Now</Table.Th>
                          <Table.Th ta="right">Change</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {review.development.map((d) => (
                          <Table.Tr key={d.player_id}>
                            <Table.Td>
                              <Position position={d.position} />
                            </Table.Td>
                            <Table.Td>
                              <Text size="sm">
                                <PlayerLink id={d.player_id} name={d.name} />
                              </Text>
                            </Table.Td>
                            <Table.Td ta="right">{d.age}</Table.Td>
                            <Table.Td ta="right">
                              <Text size="sm" c={ratingColor(d.before)} span>
                                {d.before}
                              </Text>
                            </Table.Td>
                            <Table.Td ta="right">
                              <Overall value={d.after} trend={Math.sign(d.change)} hint={{ up: 'Improved over the season', down: 'Declined over the season' }} />
                            </Table.Td>
                            <Table.Td ta="right">
                              <Text size="sm" fw={600} c={d.change > 0 ? 'green.7' : 'red.7'} span>
                                {d.change > 0 ? `+${d.change}` : `−${-d.change}`}
                              </Text>
                            </Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Table.ScrollContainer>
                )}
              </Stack>
            </Section>
            <Section value="retired" title="Retirements" count={review.retired.length}>
              {review.retired.length === 0 ? (
                <Text size="sm" c="dimmed">
                  Nobody notable retired.
                </Text>
              ) : (
                <Table verticalSpacing={4}>
                  <Table.Tbody>
                    {review.retired.map((r) => (
                      <Table.Tr key={r.player_id}>
                        <Table.Td>
                          <Position position={r.position} />
                        </Table.Td>
                        <Table.Td>
                          <Group gap="xs" wrap="nowrap">
                            <Text size="sm">
                              <PlayerLink id={r.player_id} name={r.name} />
                            </Text>
                            {r.own_player && (
                              <Badge size="xs" variant="light">
                                Yours
                              </Badge>
                            )}
                          </Group>
                          <Text size="xs" c="dimmed">
                            {r.club?.name ?? 'No club'} · {r.age}
                          </Text>
                        </Table.Td>
                        <Table.Td ta="right">
                          <Text size="sm" fw={700} c={ratingColor(r.overall)} span>
                            {r.overall}
                          </Text>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}
            </Section>
            <Section value="youth" title="Youth intake" count={review.youth.length}>
              {review.youth.length === 0 ? (
                <Text size="sm" c="dimmed">
                  No youngsters joined the academy.
                </Text>
              ) : (
                <Table verticalSpacing={4}>
                  <Table.Tbody>
                    {review.youth.map((y) => (
                      <Table.Tr key={y.player_id}>
                        <Table.Td>
                          <Position position={y.position} />
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">
                            <PlayerLink id={y.player_id} name={y.name} />
                          </Text>
                          <Text size="xs" c="dimmed">
                            {y.age} · {y.potential.label}
                          </Text>
                        </Table.Td>
                        <Table.Td ta="right">
                          <Text size="sm" fw={700} c={ratingColor(y.overall)} span>
                            {y.overall}
                          </Text>
                          <Text size="xs" c="dimmed">
                            potential {y.potential.low === y.potential.high ? y.potential.low : `${y.potential.low}–${y.potential.high}`}
                          </Text>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}
            </Section>
            {news.length > 0 && (
              <Section value="news" title="Other news" count={news.length}>
                <List spacing={4} size="sm">
                  {news.map((m, i) => (
                    <List.Item key={`${i}-${m}`}>{m}</List.Item>
                  ))}
                </List>
              </Section>
            )}
          </Accordion>
        </>
      )}
    </Stack>
  )
}
