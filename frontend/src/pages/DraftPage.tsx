import { ActionIcon, Alert, Badge, Button, Card, Group, SegmentedControl, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core'
import { useState } from 'react'

import { ApiError } from '../api/client'
import { useDraft, useDraftBoard, useSignPick } from '../api/hooks'
import type { Draft, DraftPick, DraftProspect } from '../api/types'
import ClubLink from '../components/ClubLink'
import PlayerLink from '../components/PlayerLink'
import { longDate } from '../lib/format'
import { useDevice } from '../lib/device'

/** MLS's SuperDraft: before it, the prospects and the user's own ranking (the draft takes the
 * best still there when the club is on the clock); after it, every pick, and signing the user's
 * unsigned ones. */
export default function DraftPage() {
  const draft = useDraft()
  if (draft.isError) {
    return (
      <Stack>
        <Title order={2}>SuperDraft</Title>
        <Text c="dimmed">{draft.error instanceof ApiError ? draft.error.message : 'The draft isn’t available.'}</Text>
      </Stack>
    )
  }
  const data = draft.data
  if (!data) return null
  return (
    <Stack>
      <Group justify="space-between" align="flex-end">
        <div>
          <Title order={2}>MLS SuperDraft</Title>
          <Text c="dimmed" size="sm">
            {data.season} · {longDate(data.date)} · {data.rounds} rounds · from the college prospects of the NCAA season
          </Text>
        </div>
        {data.made && <Badge variant="light">Made</Badge>}
      </Group>
      {data.made ? <Picks data={data} /> : <Board data={data} />}
    </Stack>
  )
}

function Board({ data }: { data: Draft }) {
  const { phone } = useDevice()
  const save = useDraftBoard()
  const byId = new Map(data.prospects.map((p) => [p.player_id, p]))
  const board = data.board.filter((id) => byId.has(id))
  const set = (ids: number[]) => save.mutate(ids)
  const move = (index: number, by: number) => {
    const next = [...board]
    const [item] = next.splice(index, 1)
    next.splice(index + by, 0, item!)
    set(next)
  }
  const mineFirst = data.picks.filter((p) => p.mine).map((p) => p.pick)
  return (
    <Stack>
      {data.in_mls ? (
        <Text size="sm">
          Rank the prospects you want. When your club is on the clock (picks {mineFirst.join(', ')}), it takes the best
          one still on your board; if none is left, your scouts choose. Picks join your squad if MLS’s rules allow it.
        </Text>
      ) : (
        <Text size="sm" c="dimmed">
          Only MLS clubs draft. These are the prospects the clubs will choose from.
        </Text>
      )}
      <SimpleGrid cols={phone || !data.in_mls ? 1 : 2} spacing="md">
        {data.in_mls && (
          <Card withBorder padding="sm" aria-label="Your board">
            <Title order={4} mb="xs">
              Your board
            </Title>
            {board.length === 0 && (
              <Text size="sm" c="dimmed">
                Empty: add prospects from the list.
              </Text>
            )}
            <Stack gap={4}>
              {board.map((id, i) => {
                const p = byId.get(id)!
                return (
                  <Group key={id} justify="space-between" wrap="nowrap" className="fs-row">
                    <Group gap="xs" wrap="nowrap">
                      <Text className="fs-num" w={22} c="dimmed">
                        {i + 1}
                      </Text>
                      <ProspectName p={p} />
                    </Group>
                    <Group gap={2} wrap="nowrap">
                      <ActionIcon variant="subtle" aria-label={`Move ${p.name} up`} disabled={i === 0} onClick={() => move(i, -1)}>
                        ↑
                      </ActionIcon>
                      <ActionIcon variant="subtle" aria-label={`Move ${p.name} down`} disabled={i === board.length - 1} onClick={() => move(i, 1)}>
                        ↓
                      </ActionIcon>
                      <ActionIcon variant="subtle" color="red" aria-label={`Remove ${p.name}`} onClick={() => set(board.filter((x) => x !== id))}>
                        ×
                      </ActionIcon>
                    </Group>
                  </Group>
                )
              })}
            </Stack>
          </Card>
        )}
        <Card withBorder padding="sm" aria-label="Prospects">
          <Title order={4} mb="xs">
            Prospects ({data.prospects.length})
          </Title>
          <Table.ScrollContainer minWidth={phone ? 0 : 480}>
            <Table highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Player</Table.Th>
                  <Table.Th ta="right">OVR</Table.Th>
                  <Table.Th ta="right">Potential</Table.Th>
                  {data.in_mls && <Table.Th />}
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data.prospects.map((p) => (
                  <Table.Tr key={p.player_id}>
                    <Table.Td>
                      <ProspectName p={p} />
                    </Table.Td>
                    <Table.Td ta="right" className="fs-num">
                      {p.overall}
                    </Table.Td>
                    <Table.Td ta="right" className="fs-num">
                      {p.potential_low}–{p.potential_high}
                    </Table.Td>
                    {data.in_mls && (
                      <Table.Td ta="right">
                        {p.board_rank ? (
                          <Badge variant="light">#{p.board_rank}</Badge>
                        ) : (
                          <Button size="compact-xs" variant="light" onClick={() => set([...board, p.player_id])}>
                            Add
                          </Button>
                        )}
                      </Table.Td>
                    )}
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>
      </SimpleGrid>
      <Order picks={data.picks} />
    </Stack>
  )
}

function ProspectName({ p }: { p: DraftProspect }) {
  return (
    <div>
      <Group gap={6} wrap="nowrap">
        <Text size="sm" fw={600}>
          <PlayerLink player={{ id: p.player_id, name: p.name }} />
        </Text>
        {p.ga && (
          <Badge size="xs" color="grape" variant="light" title="Generation adidas: an underclassman who declared; he sits on the supplemental roster">
            GA
          </Badge>
        )}
      </Group>
      <Text size="xs" c="dimmed">
        {p.position} · {p.college.name} · {p.class_year} · {p.age}
      </Text>
    </div>
  )
}

function Order({ picks }: { picks: DraftPick[] }) {
  const first = picks.filter((p) => p.round === 1)
  return (
    <Card withBorder padding="sm">
      <Title order={4} mb={4}>
        The order
      </Title>
      <Text size="xs" c="dimmed" mb="xs">
        Every round in this order: last season’s Supporters’ Shield table reversed, the play-off clubs after the rest and the MLS
        Cup winners last (in a first season, the table so far).
      </Text>
      <Group gap={6}>
        {first.map((p) => (
          <Badge key={p.pick} variant={p.mine ? 'filled' : 'light'} color={p.mine ? undefined : 'gray'} tt="none">
            {p.pick}. {p.club.name}
          </Badge>
        ))}
      </Group>
    </Card>
  )
}

function Picks({ data }: { data: Draft }) {
  const [round, setRound] = useState('1')
  const sign = useSignPick()
  const [error, setError] = useState<string | null>(null)
  const shown = data.picks.filter((p) => String(p.round) === round)
  const mine = data.picks.filter((p) => p.mine)
  return (
    <Stack>
      {mine.length > 0 && (
        <Card withBorder padding="sm" aria-label="Your picks">
          <Title order={4} mb="xs">
            Your picks
          </Title>
          <Stack gap={6}>
            {mine.map((p) => (
              <Group key={p.pick} justify="space-between" className="fs-row">
                <PickLine p={p} />
                {p.signed ? (
                  <Badge color="teal" variant="light">
                    Signed
                  </Badge>
                ) : (
                  <Button
                    size="compact-sm"
                    loading={sign.isPending && sign.variables === p.player_id}
                    onClick={() =>
                      p.player_id &&
                      sign.mutate(p.player_id, {
                        onSuccess: () => setError(null),
                        onError: (e) => setError(e instanceof ApiError ? e.message : 'He couldn’t be signed.'),
                      })
                    }
                  >
                    Sign
                  </Button>
                )}
              </Group>
            ))}
          </Stack>
          {error && (
            <Alert color="red" mt="xs" variant="light">
              {error}
            </Alert>
          )}
        </Card>
      )}
      <SegmentedControl
        aria-label="Round"
        value={round}
        onChange={setRound}
        data={Array.from({ length: data.rounds }, (_, k) => ({ value: String(k + 1), label: `Round ${k + 1}` }))}
      />
      <Card withBorder padding="sm">
        <Stack gap={4}>
          {shown.map((p) => (
            <Group key={p.pick} justify="space-between" wrap="nowrap" className="fs-row" fw={p.mine ? 700 : undefined}>
              <Group gap="xs" wrap="nowrap">
                <Text className="fs-num" w={28} c="dimmed">
                  {p.pick}
                </Text>
                <ClubLink club={p.club} />
              </Group>
              <PickLine p={p} right />
            </Group>
          ))}
        </Stack>
      </Card>
    </Stack>
  )
}

function PickLine({ p, right }: { p: DraftPick; right?: boolean }) {
  if (!p.player_id) return null
  return (
    <div style={{ textAlign: right ? 'right' : undefined }}>
      <Text size="sm">
        <PlayerLink player={{ id: p.player_id, name: p.name ?? '' }} />
      </Text>
      <Text size="xs" c="dimmed">
        {p.position} · {p.college}
        {right && !p.signed ? ' · unsigned' : ''}
      </Text>
    </div>
  )
}
