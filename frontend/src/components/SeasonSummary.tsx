import { Accordion, Badge, Group, Paper, Stack, Table, Text } from '@mantine/core'
import { Link } from '@tanstack/react-router'
import { useState } from 'react'
import type { MouseEvent, ReactNode } from 'react'

import { useNations } from '../api/hooks'
import type { ClubMove, Headline, Honour, Nation, SeasonFinal, SeasonReview } from '../api/types'
import { europeText } from '../lib/europeRuns'
import { type NationChoice, longDate, nationChoices, nationName, ordinal, positionColor, ratingColor } from '../lib/format'
import ClubLink from './ClubLink'
import NewsSections from './NewsSections'
import { TrebleBanner } from './EuropeHonours'
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
function Finish({ final, userClubId }: { final: SeasonFinal; userClubId: number }) {
  const treble = final.review?.headlines?.find((h) => h.kind === 'treble' && h.club.id === userClubId)
  return (
    <Stack gap={2}>
      {treble && (
        <TrebleBanner
          title={`${treble.club.name} win the Treble`}
          season={final.review?.season}
          trophies={treble.trophies ?? []}
        />
      )}
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
      {(final.europe ?? []).map((run) => (
        <Text key={run.key} size="sm">
          {run.name}: {europeText(run)}
        </Text>
      ))}
    </Stack>
  )
}

const STAR_WORDS: Record<string, string> = { '5': 'five-star', '4': 'four-star', '3': 'three-star', '2': 'two-star' }

/** A college coach's season: the program's finish, record, NCAA run and new class. */
function CollegeFinish({ final }: { final: SeasonFinal }) {
  const c = final.college
  if (!c) return null
  const signed = Object.entries(final.class_signed ?? {}).sort((a, b) => Number(b[0]) - Number(a[0]))
  const total = signed.reduce((n, [, k]) => n + k, 0)
  return (
    <Stack gap={2}>
      {c.titles.includes('national') && (
        <Paper withBorder p="xs" radius="sm" bg="var(--mantine-color-yellow-light)" style={{ borderLeft: '4px solid var(--mantine-color-yellow-6)' }}>
          <Text fw={700}>NCAA champions!</Text>
        </Paper>
      )}
      <Text fw={700}>
        {c.conference_position ? `${ordinal(c.conference_position)} in the ${c.conference_name}` : c.conference_name}
        {c.titles.includes('regular season') ? ' · Regular-season champions' : ''}
        {c.titles.includes('conference tournament') ? ' · Tournament champions' : ''}
      </Text>
      <Text size="sm" c="dimmed">
        Won {c.won}, drawn {c.drawn}, lost {c.lost} · goals {c.goals_for}–{c.goals_against}
        {c.rpi_rank ? ` · ${ordinal(c.rpi_rank)} in the RPI` : ''}
      </Text>
      <Text size="sm">{c.ncaa ?? 'Not in the NCAA tournament'}</Text>
      <Text size="sm">
        New class: {total === 0 ? 'nobody signed' : signed.map(([st, k]) => `${k} ${STAR_WORDS[st] ?? `${st}-star`}`).join(', ')}
      </Text>
    </Stack>
  )
}

function ConferenceChampionsTable({ final, userClubId }: { final: SeasonFinal; userClubId: number }) {
  const rows = final.conference_champions ?? []
  if (rows.length === 0) return <Text size="sm" c="dimmed">No conference champions this season.</Text>
  const bold = (id?: number) => (id === userClubId ? 700 : 500)
  return (
    <Table verticalSpacing={4}>
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Conference</Table.Th>
          <Table.Th>Regular season</Table.Th>
          <Table.Th>Tournament</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {rows.map((r) => (
          <Table.Tr key={r.conference}>
            <Table.Td>
              <Text size="sm">{r.conference}</Text>
            </Table.Td>
            <Table.Td>
              <Text size="sm" fw={bold(r.regular_season?.id)}>
                {r.regular_season ? <ClubLink club={r.regular_season} /> : '–'}
              </Text>
            </Table.Td>
            <Table.Td>
              <Text size="sm" fw={bold(r.tournament?.id)}>
                {r.tournament ? <ClubLink club={r.tournament} /> : '–'}
              </Text>
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  )
}

/** How the squad's overalls moved over the season. */
function DevelopmentTable({ review }: { review: SeasonReview }) {
  return (
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

function Champions({ honours }: { honours: Honour[] }) {
  if (honours.length === 0) return <Text size="sm" c="dimmed">No competitions here.</Text>
  const rows = [...honours].sort((a, b) => Number(a.kind === 'cup') - Number(b.kind === 'cup') || a.tier - b.tier || a.name.localeCompare(b.name))
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

function Moves({ moves, userClubId, none, promotion }: { moves: ClubMove[]; userClubId: number; none: string; promotion?: boolean }) {
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
                {m.via_playoffs ? (
                  <Badge size="xs" variant="light" color="teal">
                    Play-offs
                  </Badge>
                ) : !promotion ? null : m.position === 1 ? (
                  <Badge size="xs" variant="light" color="yellow">
                    Champions
                  </Badge>
                ) : (
                  <Badge size="xs" variant="light" color="gray">
                    Automatic
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

const HEADLINE_STYLE: Record<string, { label: string; color: string }> = {
  treble: { label: 'Treble', color: 'yellow' },
  league_title: { label: 'Champions', color: 'yellow' },
  cup_upset: { label: 'Cup upset', color: 'grape' },
  continental_title: { label: 'Europe', color: 'yellow' },
}

/** The season's notable results (the major leagues' champions, cup upsets), as highlights. */
function Headlines({ headlines }: { headlines: Headline[] }) {
  return (
    <Stack gap={6}>
      {headlines.map((h, i) => {
        const style = HEADLINE_STYLE[h.kind] ?? { label: 'News', color: 'gray' }
        return (
          <Paper
            key={`${h.kind}-${h.competition}-${i}`}
            withBorder
            p="xs"
            radius="sm"
            style={{ borderLeft: `4px solid var(--mantine-color-${style.color}-6)` }}
            bg={`var(--mantine-color-${style.color}-light)`}
          >
            <Group gap="xs" wrap="nowrap" align="flex-start">
              <Badge size="xs" variant="filled" color={style.color} w={74} style={{ flexShrink: 0 }}>
                {style.label}
              </Badge>
              <div>
                <Text size="sm" fw={600}>
                  {h.text}
                </Text>
                {h.detail && (
                  <Text size="xs" c="dimmed">
                    {h.detail}
                  </Text>
                )}
              </div>
            </Group>
          </Paper>
        )
      })}
    </Stack>
  )
}

/** The nations the summary has something to say about, in the order the pickers list them (the
 * server's ranking when it has sent it, else the big five first and then by name). Each comes with
 * the names of the leagues and cups the summary mentions for it, which the country search matches. */
function nationsOf(final: SeasonFinal, ranked?: Nation[]): (NationChoice & { leagues: { name: string }[] })[] {
  const review = final.review
  if (!review) return []
  const names = new Map<string, Set<string>>()
  const add = (nation: string, name: string) => {
    if (nation) names.set(nation, (names.get(nation) ?? new Set<string>()).add(name))
  }
  for (const h of review.honours) add(h.nation, h.name)
  for (const m of [...review.promoted, ...review.relegated]) {
    add(m.nation, m.from_league)
    add(m.nation, m.to_league)
  }
  return nationChoices(names.keys(), ranked).map((n) => ({ ...n, leagues: [...(names.get(n.code) ?? [])].map((name) => ({ name })) }))
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
  const nations = nationsOf(final, useNations().data)
  const nation = picked ?? (nations.some((n) => n.code === userNation) ? userNation : nations[0]?.code) ?? ''
  const country = nations.find((n) => n.code === nation)?.name ?? nationName(nation)
  const news = final.news ?? []
  const headlines = review?.headlines ?? []

  // Following a link from inside closes the window holding the summary.
  const closeOnLink = (e: MouseEvent<HTMLElement>) => {
    if ((e.target as HTMLElement).closest('a')) onNavigate()
  }

  return (
    <Stack gap="sm" onClickCapture={closeOnLink}>
      {final.college ? <CollegeFinish final={final} /> : <Finish final={final} userClubId={userClubId} />}
      {review && final.college && (
        <>
          <Text size="sm" c="dimmed">
            {review.next_season ? `The ${review.next_season} season begins.` : `The ${review.season} season is over.`}
            {final.national_champion ? ` ${final.national_champion.name} won the College Cup.` : ''}
          </Text>
          <Accordion multiple variant="separated" defaultValue={['conferences', 'development']}>
            <Section value="conferences" title="Conference champions" count={(final.conference_champions ?? []).length}>
              <ConferenceChampionsTable final={final} userClubId={userClubId} />
            </Section>
            <Section value="development" title="Your squad's development" count={review.development.length}>
              <DevelopmentTable review={review} />
            </Section>
            {news.length > 0 && (
              <Section value="news" title="Other news" count={news.length}>
                <NewsSections sections={final.news_sections} messages={news} />
              </Section>
            )}
          </Accordion>
        </>
      )}
      {review && !final.college && (
        <>
          <Stack gap="xs">
            <Text size="sm" c="dimmed">
              {review.next_season ? `The ${review.next_season} season begins.` : `The ${review.season} season is over.`}
            </Text>
            <NationPicker nations={nations} value={nation} onChange={setPicked} home={userNation} />
          </Stack>
          <Accordion multiple variant="separated" defaultValue={['champions', 'promoted', 'development']}>
            <Section value="champions" title={`Champions${country ? ` · ${country}` : ''}`}>
              <Champions honours={review.honours.filter((h) => h.nation === nation)} />
            </Section>
            <Section value="promoted" title={`Promoted${country ? ` · ${country}` : ''}`}>
              <Moves moves={review.promoted.filter((m) => m.nation === nation)} userClubId={userClubId} none="No club went up." promotion />
            </Section>
            <Section value="relegated" title={`Relegated${country ? ` · ${country}` : ''}`}>
              <Moves moves={review.relegated.filter((m) => m.nation === nation)} userClubId={userClubId} none="No club went down." />
            </Section>
            <Section value="development" title="Your squad's development" count={review.development.length}>
              <DevelopmentTable review={review} />
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
            {headlines.length + news.length > 0 && (
              <Section value="news" title="Other news" count={headlines.length + news.length}>
                <Stack gap="sm">
                  {headlines.length > 0 && <Headlines headlines={headlines} />}
                  {news.length > 0 && <NewsSections sections={final.news_sections} messages={news} />}
                </Stack>
              </Section>
            )}
          </Accordion>
        </>
      )}
    </Stack>
  )
}
