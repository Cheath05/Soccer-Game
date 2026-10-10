import { Anchor, Badge, Card, Group, Loader, SegmentedControl, Stack, Table, Text } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import { type OverviewPlayer, type OverviewProspect, useMarketOverview } from '../api/transfers'
import type { ClubRef } from '../api/types'
import { money, positionColor, ratingColor, shortDate } from '../lib/format'
import ClubLink from './ClubLink'

function PlayerLink({ player }: { player: ClubRef }) {
  const navigate = useNavigate()
  return (
    <Anchor size="sm" fw={500} onClick={() => void navigate({ to: '/players/$playerId', params: { playerId: String(player.id) } })}>
      {player.name}
    </Anchor>
  )
}

function Club({ club, fallback }: { club: ClubRef | null; fallback: string }) {
  return club ? <ClubLink club={club} /> : <Text span size="sm" c="dimmed">{fallback}</Text>
}

/** Top transfers, the most valuable players and the best young prospects across the world. */
export default function MarketOverview() {
  const overview = useMarketOverview()
  const [view, setView] = useState('transfers')
  if (overview.isPending) return <Loader />
  if (!overview.data) return <Text c="red">{overview.error?.message}</Text>
  const o = overview.data
  const rows: (OverviewPlayer & Partial<OverviewProspect>)[] = view === 'prospects' ? o.prospects : o.most_valuable
  return (
    <Stack>
      <Group justify="space-between">
        <SegmentedControl
          value={view}
          onChange={setView}
          data={[
            { value: 'transfers', label: 'Top transfers' },
            { value: 'valuable', label: 'Most valuable' },
            { value: 'prospects', label: 'Top prospects' },
          ]}
        />
        <Text size="xs" c="dimmed">
          {o.season}
          {view === 'prospects' ? ' · aged 21 or under, ranked by the potential your scouts see' : ''}
        </Text>
      </Group>
      <Card withBorder p={0}>
        <Table.ScrollContainer minWidth={640}>
          {view === 'transfers' && (
            <Table highlightOnHover striped>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Date</Table.Th>
                  <Table.Th>Player</Table.Th>
                  <Table.Th>Pos</Table.Th>
                  <Table.Th ta="right">OVR</Table.Th>
                  <Table.Th>Move</Table.Th>
                  <Table.Th ta="right">Fee</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {o.biggest_transfers.length === 0 && (
                  <Table.Tr>
                    <Table.Td colSpan={6}>
                      <Text c="dimmed" size="sm">No transfers with a fee yet this season.</Text>
                    </Table.Td>
                  </Table.Tr>
                )}
                {o.biggest_transfers.map((t, i) => (
                  <Table.Tr key={`${t.player.id}-${i}`} fw={t.yours ? 600 : undefined}>
                    <Table.Td c="dimmed">{shortDate(t.date)}</Table.Td>
                    <Table.Td><PlayerLink player={t.player} /></Table.Td>
                    <Table.Td>{t.position && <Badge size="sm" variant="light" color={positionColor(t.position)}>{t.position}</Badge>}</Table.Td>
                    <Table.Td ta="right" fw={700}>{t.overall ?? '–'}</Table.Td>
                    <Table.Td>
                      <Club club={t.from_club} fallback="Free agent" /> → <Club club={t.to_club} fallback="released" />
                    </Table.Td>
                    <Table.Td ta="right" fw={600}>{money(t.fee_eur)}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
          {view !== 'transfers' && (
            <Table highlightOnHover striped>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th w={36}>#</Table.Th>
                  <Table.Th>Player</Table.Th>
                  <Table.Th>Pos</Table.Th>
                  <Table.Th ta="right">Age</Table.Th>
                  <Table.Th ta="right">OVR</Table.Th>
                  {view === 'prospects' && <Table.Th>Potential</Table.Th>}
                  <Table.Th>Club</Table.Th>
                  <Table.Th ta="right">Value</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {rows.map((p, i) => (
                  <Table.Tr key={p.player.id}>
                    <Table.Td c="dimmed">{i + 1}</Table.Td>
                    <Table.Td><PlayerLink player={p.player} /></Table.Td>
                    <Table.Td><Badge size="sm" variant="light" color={positionColor(p.position)}>{p.position}</Badge></Table.Td>
                    <Table.Td ta="right">{p.age}</Table.Td>
                    <Table.Td ta="right" fw={700} c={ratingColor(p.overall)}>{p.overall}</Table.Td>
                    {view === 'prospects' && (
                      <Table.Td title={p.potential_label}>
                        <Text span size="sm" fw={600}>{p.potential_low}–{p.potential_high}</Text>
                      </Table.Td>
                    )}
                    <Table.Td><Club club={p.club} fallback="Free agent" /></Table.Td>
                    <Table.Td ta="right">{money(p.value_eur)}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Table.ScrollContainer>
      </Card>
    </Stack>
  )
}
