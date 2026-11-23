import { Badge, Card, Group, NativeSelect, ScrollArea, Stack, Table, Text } from '@mantine/core'
import { useState } from 'react'

import type { AllDivision } from '../api/americas'
import { shortDate } from '../lib/format'
import { useDevice } from '../lib/device'
import ClubLink from './ClubLink'
import { MatchCard } from './CollegeBracket'

// The All-Division Tournament (api/college.py /all-division): D-I, D-II and D-III's best after the
// national finals, on a set bracket (data/config/college/lower.yaml). Teams enter in different
// rounds, so it isn't a tree of pairs: the rounds stand side by side as lists on a computer, one
// at a time on a phone, each match saying where an undecided side comes from. Below them, the
// field by the round it enters.

const DIVISION_COLOR: Record<number, string> = { 1: 'blue', 2: 'teal', 3: 'grape' }

export function DivisionBadge({ division, name }: { division: number; name: string }) {
  return (
    <Badge size="xs" variant="light" color={DIVISION_COLOR[division] ?? 'gray'} style={{ flexShrink: 0 }}>
      {name}
    </Badge>
  )
}

/** The first round with a match still to play, or the last. */
function liveRound(t: AllDivision): number {
  const open = t.rounds.findIndex((r) => r.matches.some((m) => !m.winner))
  return open === -1 ? t.rounds.length - 1 : open
}

export default function AllDivisionBracket({ tournament: t }: { tournament: AllDivision }) {
  const { phone } = useDevice()
  const [picked, setPicked] = useState<number | null>(null)
  const division = new Map(t.entrants.map((e) => [e.seed, e]))
  if (t.entrants.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        The field is picked on {shortDate(t.selection)}, once D-I’s College Cup and the D-II and D-III finals are played: each division’s national champion, then its best by the RPI. A set bracket, mixed across the divisions; D-II and D-III’s top two meet none of D-I’s top four before the quarterfinals. D-I’s top four start in the Round of 16 (two byes); D-I’s next four and the top four of D-II and D-III start in the second round.
      </Text>
    )
  }
  const live = liveRound(t)
  const round = picked ?? live
  const label = (seed: number | undefined) => {
    const e = seed === undefined ? undefined : division.get(seed)
    return e ? <DivisionBadge division={e.division} name={e.division_name} /> : null
  }
  const Round = ({ index }: { index: number }) => {
    const r = t.rounds[index]
    return (
      <Stack gap={8}>
        {r.matches.map((m) => (
          <div key={m.index}>
            <Group gap={4} mb={2}>
              <Text size="xs" c="dimmed">
                {m.index + 1}
              </Text>
              {label(m.a?.seed)}
              {m.a && m.b && (
                <Text size="xs" c="dimmed">
                  v
                </Text>
              )}
              {label(m.b?.seed)}
            </Group>
            <MatchCard match={m} />
          </div>
        ))}
      </Stack>
    )
  }

  return (
    <Stack gap="sm">
      {t.champion && (
        <Card className="fs-hero" padding="md">
          <span className="fs-label">All-Division champions{t.champion_division ? ` · ${t.champion_division}` : ''}</span>
          <Text className="fs-num" fz={28} lh={1.1} tt="uppercase">
            <ClubLink club={t.champion} />
          </Text>
          <Text size="xs" mt={4}>
            The best team in college soccer this season.
          </Text>
        </Card>
      )}
      {phone ? (
        <>
          <NativeSelect aria-label="Round" value={String(round)} onChange={(e) => setPicked(Number(e.currentTarget.value))} data={t.rounds.map((r) => ({ value: String(r.round), label: `${r.name} · ${shortDate(r.date)}` }))} />
          <Round index={round} />
        </>
      ) : (
        <ScrollArea type="auto" offsetScrollbars>
          <Group align="flex-start" wrap="nowrap" gap="sm">
            {t.rounds.map((r) => (
              <Stack key={r.round} gap={6} w={240} style={{ flexShrink: 0 }}>
                <div>
                  <span className="fs-label">{r.name}</span>
                  <Text size="xs" c="dimmed">
                    {shortDate(r.date)}
                  </Text>
                </div>
                <Round index={r.round} />
              </Stack>
            ))}
          </Group>
        </ScrollArea>
      )}
      <Card withBorder padding="sm">
        <Text fw={700} size="sm">
          The field
        </Text>
        <Text size="xs" c="dimmed" mb={4}>
          A set bracket, mixed across the divisions: D-II and D-III’s top two meet none of D-I’s top four before the quarterfinals. Seeded as one list (the later a team starts, the better its seed): the better seed is at home until the semifinals.
        </Text>
        <Table verticalSpacing={3} highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th w={40}>Seed</Table.Th>
              <Table.Th>School</Table.Th>
              <Table.Th>Division</Table.Th>
              <Table.Th visibleFrom="sm">Starts in</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {t.entrants.map((e) => (
              <Table.Tr key={e.seed}>
                <Table.Td className="fs-num">{e.seed}</Table.Td>
                <Table.Td>
                  <Text size="sm" fw={500} span>
                    <ClubLink club={e.club} />
                  </Text>
                  <Text size="xs" c="dimmed" hiddenFrom="sm">
                    Starts in the {e.enters.toLowerCase()}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Group gap={4} wrap="nowrap">
                    <DivisionBadge division={e.division} name={e.division_name} />
                    <Text size="xs" c="dimmed">
                      {e.rank === 1 ? 'champions' : `#${e.rank}`}
                    </Text>
                  </Group>
                </Table.Td>
                <Table.Td visibleFrom="sm">
                  <Text size="sm">{e.enters}</Text>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Card>
    </Stack>
  )
}
