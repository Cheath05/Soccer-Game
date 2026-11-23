import { Badge, Card, Group, NativeSelect, Stack, Switch, Table, Text } from '@mantine/core'
import { useState } from 'react'

import { type DraftHistoryPick, useDraftHistory } from '../api/americas'
import { useDevice } from '../lib/device'
import { money, positionColor, ratingColor } from '../lib/format'
import ClubLink from './ClubLink'
import PlayerLink from './PlayerLink'

// The SuperDraft's history (api/draft.py /history): every pick of every draft in the career,
// where he came from (a college coach's alumni marked) and how he has done since: where he plays,
// his overall and value now, and his professional appearances and goals.

function Now({ p }: { p: DraftHistoryPick }) {
  if (p.now === 'retired') return <>Retired</>
  if (p.now === 'free_agent' || !p.club) return <>Free agent</>
  return <ClubLink club={p.club} />
}

export default function DraftHistory({ college }: { college: boolean }) {
  const { phone } = useDevice()
  const history = useDraftHistory(true)
  const [season, setSeason] = useState<string | null>(null)
  const [alumni, setAlumni] = useState(false)
  if (!history.data) return history.error ? <Text c="red">{history.error.message}</Text> : null
  const seasons = [...new Set(history.data.map((p) => p.season))]
  if (seasons.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        No SuperDraft yet: the first is in January, after the College Cup.
      </Text>
    )
  }
  // Your alumni across every draft; otherwise one draft at a time.
  const shown = season ?? seasons[0]
  const rows = history.data.filter((p) => (alumni ? p.alumnus : p.season === shown))
  const mine = history.data.filter((p) => p.alumnus)
  return (
    <Stack gap="sm">
      <Group gap="sm">
        {!alumni && (
          <NativeSelect size="xs" aria-label="Draft" value={shown} onChange={(e) => setSeason(e.currentTarget.value)} data={seasons.map((s) => ({ value: s, label: `${s} draft` }))} />
        )}
        {college && <Switch size="sm" label={`My alumni (${mine.length})`} checked={alumni} onChange={(e) => setAlumni(e.currentTarget.checked)} />}
      </Group>
      {rows.length === 0 ? (
        <Text size="sm" c="dimmed">
          {alumni ? 'None of your players has been drafted yet.' : 'No picks.'}
        </Text>
      ) : phone ? (
        <Stack gap={6}>
          {rows.map((p) => (
            <Card key={`${p.season}-${p.pick}`} withBorder padding="xs" bg={p.alumnus && !alumni ? 'var(--mantine-color-blue-light)' : undefined}>
              <Group gap={6} wrap="nowrap">
                <Text size="xs" c="dimmed" w={52} style={{ flexShrink: 0 }}>
                  {alumni ? p.season.slice(0, 4) + ' ' : ''}#{p.pick}
                </Text>
                <Badge color={positionColor(p.position)} variant="light" size="sm" w={40} style={{ flexShrink: 0 }}>
                  {p.position}
                </Badge>
                <Text size="sm" fw={600} truncate style={{ flex: 1, minWidth: 0 }}>
                  <PlayerLink player={{ id: p.player_id, name: p.name }} />
                </Text>
                <Text className="fs-num" fz={20} c={ratingColor(p.overall)} style={{ flexShrink: 0 }}>
                  {p.overall}
                </Text>
              </Group>
              <Text size="xs" c="dimmed" truncate>
                By {p.mls_club.name} from {p.college?.name ?? '–'}
                {p.ga ? ' (GA)' : ''}
              </Text>
              <Text size="xs" truncate>
                Now: <Now p={p} /> · {money(p.value_eur)} · {p.pro_apps} apps, {p.pro_goals} goals, {p.pro_assists} assists
              </Text>
            </Card>
          ))}
        </Stack>
      ) : (
        <Table.ScrollContainer minWidth={900}>
          <Table striped highlightOnHover verticalSpacing={4}>
            <Table.Thead>
              <Table.Tr>
                {alumni && <Table.Th>Draft</Table.Th>}
                <Table.Th>Pick</Table.Th>
                <Table.Th>Player</Table.Th>
                <Table.Th>Picked by</Table.Th>
                <Table.Th>From</Table.Th>
                <Table.Th>Now</Table.Th>
                <Table.Th ta="right">Ovr</Table.Th>
                <Table.Th ta="right">Value</Table.Th>
                <Table.Th ta="right" title="Professional appearances, goals and assists since the draft">
                  Pro apps / G / A
                </Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((p) => (
                <Table.Tr key={`${p.season}-${p.pick}`} bg={p.alumnus && !alumni ? 'var(--mantine-color-blue-light)' : undefined}>
                  {alumni && <Table.Td>{p.season}</Table.Td>}
                  <Table.Td className="fs-num">
                    {p.pick}{' '}
                    <Text span size="xs" c="dimmed">
                      (R{p.round})
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Group gap={6} wrap="nowrap">
                      <Badge color={positionColor(p.position)} variant="light" size="sm" w={40}>
                        {p.position}
                      </Badge>
                      <Text size="sm" fw={600}>
                        <PlayerLink player={{ id: p.player_id, name: p.name }} />
                      </Text>
                      {p.ga && (
                        <Badge size="xs" color="grape" title="Generation adidas: declared early">
                          GA
                        </Badge>
                      )}
                      {!p.signed && (
                        <Badge size="xs" color="gray" title="Not signed by the club that picked him">
                          Unsigned
                        </Badge>
                      )}
                    </Group>
                  </Table.Td>
                  <Table.Td>
                    <ClubLink club={p.mls_club} />
                  </Table.Td>
                  <Table.Td>
                    {p.college ? <ClubLink club={p.college} /> : '–'}
                    {p.alumnus && (
                      <Badge ml={6} size="xs" color="blue">
                        Yours
                      </Badge>
                    )}
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">
                      <Now p={p} />
                    </Text>
                  </Table.Td>
                  <Table.Td ta="right" className="fs-num" c={ratingColor(p.overall)}>
                    {p.overall}
                  </Table.Td>
                  <Table.Td ta="right">{money(p.value_eur)}</Table.Td>
                  <Table.Td ta="right" className="fs-num">
                    {p.pro_apps} / {p.pro_goals} / {p.pro_assists}
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
