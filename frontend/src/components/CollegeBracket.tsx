import { Card, Group, NativeSelect, ScrollArea, Stack, Text } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import type { Bracket, BracketMatch, BracketSide } from '../api/americas'
import { shortDate } from '../lib/format'
import { useDevice } from '../lib/device'
import ClubLink from './ClubLink'

// A college tournament's bracket (api/college.py /bracket): the NCAA's or a conference's. Matches
// 2i and 2i+1 of a round feed match i of the next, so on a computer the rounds stand side by side
// as a tree (each match centred on the two it comes from); on a phone, one round at a time.

/** The first round with a match still to be decided (byes aside), or the last round. */
function liveRound(bracket: Bracket): number {
  const open = bracket.rounds.findIndex((r) => r.matches.some((m) => !m.bye && !m.winner))
  return open === -1 ? bracket.rounds.length - 1 : open
}

export default function CollegeBracket({ bracket, empty }: { bracket: Bracket; empty: string }) {
  const { phone } = useDevice()
  const total = bracket.rounds.length
  // On a computer the tree shows at most five rounds (16 rows); from the live round on, once it's
  // under way.
  const [start, setStart] = useState<number | null>(null)
  const [phoneRound, setPhoneRound] = useState<number | null>(null)
  if (total === 0) {
    return (
      <Text size="sm" c="dimmed">
        {empty}
      </Text>
    )
  }
  const live = liveRound(bracket)
  // Once it's over, the whole tree that fits; while it's on, from the round being played.
  const from = start ?? (bracket.champion ? Math.max(0, total - 5) : Math.max(0, total - 5, Math.min(live, total - 2)))
  const round = phoneRound ?? live
  const rounds = bracket.rounds.map((r) => ({ value: String(r.round), label: `${r.name} · ${shortDate(r.date)}` }))

  return (
    <Stack gap="sm">
      {bracket.champion && (
        <Card className="fs-hero" padding="md">
          <span className="fs-label">{bracket.event === 'NCAA' ? 'NCAA champions' : `${bracket.name} champions`}</span>
          <Text className="fs-num" fz={28} lh={1.1} tt="uppercase">
            <ClubLink club={bracket.champion} />
          </Text>
        </Card>
      )}
      {phone ? (
        <>
          <NativeSelect aria-label="Round" value={String(round)} onChange={(e) => setPhoneRound(Number(e.currentTarget.value))} data={rounds} />
          <Stack gap={8}>
            {bracket.rounds[round].matches.map((m) => (
              <MatchCard key={m.index} match={m} />
            ))}
          </Stack>
        </>
      ) : (
        <>
          {total > 2 && (
            <Group gap="xs">
              <Text size="sm" c="dimmed">
                From
              </Text>
              <NativeSelect
                size="xs"
                aria-label="From round"
                value={String(from)}
                onChange={(e) => setStart(Number(e.currentTarget.value))}
                data={bracket.rounds.slice(0, total - 1).map((r) => ({ value: String(r.round), label: r.name }))}
              />
            </Group>
          )}
          <Tree bracket={bracket} from={from} />
        </>
      )}
    </Stack>
  )
}

function Tree({ bracket, from }: { bracket: Bracket; from: number }) {
  const shown = bracket.rounds.slice(from)
  const rows = shown[0].matches.length
  return (
    <ScrollArea type="auto" offsetScrollbars>
      <div
        className="fs-bracket"
        style={{ gridTemplateColumns: `repeat(${shown.length}, minmax(190px, 1fr))`, gridTemplateRows: `auto repeat(${rows}, minmax(64px, auto))` }}
      >
        {shown.map((r, column) => (
          <div key={`h${r.round}`} className="fs-bracket-head" style={{ gridColumn: column + 1, gridRow: 1 }}>
            <span className="fs-label">{r.name}</span>
            <Text size="xs" c="dimmed">
              {shortDate(r.date)}
            </Text>
          </div>
        ))}
        {shown.map((r, column) =>
          r.matches.map((m) => {
            const span = 2 ** column
            return (
              <div key={`${r.round}-${m.index}`} className="fs-bracket-cell" style={{ gridColumn: column + 1, gridRow: `${m.index * span + 2} / span ${span}` }}>
                <MatchCard match={m} />
              </div>
            )
          }),
        )}
      </div>
    </ScrollArea>
  )
}

/** A side's goals and penalties, whichever end it played at. */
function goals(m: BracketMatch, side: BracketSide | null): { goals: number | null; pens: number | null } {
  if (!side || m.home_goals === null || m.away_goals === null) return { goals: null, pens: null }
  const home = m.home_club_id === side.club.id
  return { goals: home ? m.home_goals : m.away_goals, pens: home ? m.home_pens : m.away_pens }
}

export function MatchCard({ match }: { match: BracketMatch }) {
  const navigate = useNavigate()
  const played = match.fixture_id !== null && match.home_goals !== null
  const open = () => played && void navigate({ to: '/match/$fixtureId', params: { fixtureId: String(match.fixture_id) } })
  if (match.bye) {
    return (
      <div className="fs-match" data-bye>
        <Line side={match.a} won />
        <Text size="xs" c="dimmed" pl={24}>
          Bye to the next round
        </Text>
      </div>
    )
  }
  const decided = match.winner !== null
  const notes = [
    match.date ? shortDate(match.date) : null,
    match.neutral ? 'neutral' : null,
    match.extra_time && match.home_pens === null ? 'aet' : null,
    match.home_pens !== null ? 'pens' : null,
  ].filter(Boolean)
  return (
    <div className="fs-match" data-played={played || undefined} onClick={open} role={played ? 'link' : undefined} aria-label={played ? 'Match report' : undefined}>
      <Line side={match.a} from={match.a_from} {...goals(match, match.a)} won={decided && match.winner?.seed === match.a?.seed} lost={decided && match.winner?.seed !== match.a?.seed} />
      <Line side={match.b} from={match.b_from} {...goals(match, match.b)} won={decided && match.winner?.seed === match.b?.seed} lost={decided && match.winner?.seed !== match.b?.seed} />
      {notes.length > 0 && <div className="fs-match-note">{notes.join(' · ')}</div>}
    </div>
  )
}

function Line({ side, from, goals, pens, won, lost }: { side: BracketSide | null; from?: string | null; goals?: number | null; pens?: number | null; won?: boolean; lost?: boolean }) {
  return (
    <div className="fs-match-line" data-won={won || undefined} data-lost={lost || undefined}>
      <span className="fs-match-seed">{side?.seed ?? ''}</span>
      <span className="fs-match-name">{side ? <ClubLink club={side.club} /> : <Text span size="xs" c="dimmed">{from ?? 'To be decided'}</Text>}</span>
      {goals !== null && goals !== undefined && (
        <span className="fs-match-score">
          {goals}
          {pens !== null && pens !== undefined && <small> ({pens})</small>}
        </span>
      )}
    </div>
  )
}
