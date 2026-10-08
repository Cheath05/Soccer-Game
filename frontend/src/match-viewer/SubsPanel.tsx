import { Badge, Button, Checkbox, Group, Progress, ScrollArea, SegmentedControl, Stack, Table, Text, Tooltip } from '@mantine/core'
import { useState } from 'react'

import { POSITION_ORDER, matchRatingColor } from '../lib/format'
import type { BenchStatus, PlayerStatus } from './protocol'
import SubsPitch from './SubsPitch'
import type { LiveMatch } from './useLiveMatch'

function energyColor(value: number): string {
  return value > 75 ? 'teal' : value > 60 ? 'yellow' : 'red'
}

export function Ovr({ value }: { value: number }) {
  return (
    <Tooltip label="Overall: long-term ability in this position">
      <Badge variant="light" color="gray" size="sm" radius="sm">
        {value}
      </Badge>
    </Tooltip>
  )
}

export function MatchRating({ value }: { value: number }) {
  return (
    <Tooltip label="Match rating: how well he is playing today (6.0 is average)">
      <Text span fw={700} size="sm" c={matchRatingColor(value)}>
        {value.toFixed(1)}
      </Text>
    </Tooltip>
  )
}

function Cards({ player }: { player: PlayerStatus }) {
  if (player.red) return <>🟥</>
  return <>{player.yellow ? '🟨' : ''}</>
}

// Everything needed to choose a substitution; the choice stays the manager's.
export default function SubsPanel({ match, onInspect }: { match: LiveMatch; onInspect: (index: number) => void }) {
  const { live, send } = match
  const [off, setOff] = useState<number | null>(null)
  const [on, setOn] = useState<number | null>(null)
  const [view, setView] = useState('pitch')
  if (!live) return null
  const team = live.userTeam
  const players = live.status.players
    .filter((p) => p.team === team && p.active)
    .sort((a, b) => POSITION_ORDER.indexOf(a.position) - POSITION_ORDER.indexOf(b.position))
  const bench: BenchStatus[] = live.status.bench[team] ?? []
  const leaving = players.find((p) => p.player_id === off)
  const coming = bench.find((b) => b.player_id === on)
  const left = live.subsLeft[team]
  const waiting = live.pendingSubs?.[team] ?? []
  const nameOf = (id: number) =>
    players.find((p) => p.player_id === id)?.short_name ?? bench.find((b) => b.player_id === id)?.short_name ?? '?'
  const dead = live.paused || live.atBreak || live.restart !== null
  return (
    <Stack gap="xs">
      <Group justify="space-between">
        <Text size="sm">
          Substitutions left: <b>{left}</b>
        </Text>
        <Checkbox
          size="xs"
          label="Assistant makes subs"
          checked={live.autoSubs[team]}
          onChange={(e) => send({ type: 'auto_subs', value: e.currentTarget.checked })}
        />
      </Group>
      <SegmentedControl size="xs" value={view} onChange={setView} data={[{ value: 'pitch', label: 'Pitch' }, { value: 'list', label: 'List' }]} />
      {view === 'pitch' && <SubsPitch match={match} onInspect={onInspect} />}
      {view === 'list' && (<>
      <ScrollArea h={210} type="auto">
        <Table verticalSpacing={1} horizontalSpacing={4} highlightOnHover striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>#</Table.Th>
              <Table.Th>On the pitch</Table.Th>
              <Table.Th>Pos</Table.Th>
              <Table.Th ta="center">OVR</Table.Th>
              <Table.Th ta="center">Rating</Table.Th>
              <Table.Th>Energy</Table.Th>
              <Table.Th ta="right">Cond</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {players.map((p) => (
              <Table.Tr
                key={p.player_id}
                bg={off === p.player_id ? 'var(--mantine-color-orange-light)' : undefined}
                style={{ cursor: 'pointer' }}
                onClick={() => setOff(off === p.player_id ? null : p.player_id)}
              >
                <Table.Td>{p.number}</Table.Td>
                <Table.Td>
                  <Text
                    size="sm"
                    td="underline dotted"
                    onClick={(event) => {
                      event.stopPropagation()
                      onInspect(p.index)
                    }}
                  >
                    {p.short_name}
                  </Text>
                </Table.Td>
                <Table.Td>{p.position}</Table.Td>
                <Table.Td ta="center">
                  <Ovr value={p.ovr} />
                </Table.Td>
                <Table.Td ta="center">
                  <MatchRating value={p.rating} />
                </Table.Td>
                <Table.Td w={70}>
                  <Tooltip label={`${p.energy}% energy left`}>
                    <Progress value={p.energy} size="sm" color={energyColor(p.energy)} />
                  </Tooltip>
                </Table.Td>
                <Table.Td ta="right">
                  <Tooltip label="Match fitness when the game started">
                    <Text span size="xs" c="dimmed">
                      {p.condition}%
                    </Text>
                  </Tooltip>
                </Table.Td>
                <Table.Td>
                  <Cards player={p} />
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </ScrollArea>
      <ScrollArea h={170} type="auto">
        <Table verticalSpacing={1} horizontalSpacing={4} highlightOnHover striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>#</Table.Th>
              <Table.Th>Bench</Table.Th>
              <Table.Th>Pos</Table.Th>
              <Table.Th ta="center">OVR</Table.Th>
              <Table.Th ta="center">
                <Tooltip label="Overall in the position of the player you're taking off">
                  <span>{leaving ? `as ${leaving.position}` : 'In slot'}</span>
                </Tooltip>
              </Table.Th>
              <Table.Th ta="right">Cond</Table.Th>
              <Table.Th ta="right">Age</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {bench.map((b) => {
              const fit = leaving && b.fit ? b.fit[String(leaving.player_id)] : undefined
              return (
                <Table.Tr
                  key={b.player_id}
                  bg={on === b.player_id ? 'var(--mantine-color-teal-light)' : undefined}
                  style={{ cursor: 'pointer' }}
                  onClick={() => setOn(on === b.player_id ? null : b.player_id)}
                >
                  <Table.Td>{b.number}</Table.Td>
                  <Table.Td>{b.short_name}</Table.Td>
                  <Table.Td>
                    <Tooltip label={b.positions.join(', ') || b.position}>
                      <span>{b.position}</span>
                    </Tooltip>
                  </Table.Td>
                  <Table.Td ta="center">
                    <Ovr value={b.ovr} />
                  </Table.Td>
                  <Table.Td ta="center">{fit !== undefined ? <Ovr value={fit} /> : '–'}</Table.Td>
                  <Table.Td ta="right">
                    <Text span size="xs" c="dimmed">
                      {b.condition}%
                    </Text>
                  </Table.Td>
                  <Table.Td ta="right">{b.age}</Table.Td>
                </Table.Tr>
              )
            })}
          </Table.Tbody>
        </Table>
      </ScrollArea>
      <Button
        disabled={!leaving || !coming || left <= 0 || live.finished}
        onClick={() => {
          send({ type: 'sub', out: off, in: on })
          setOff(null)
          setOn(null)
        }}
      >
        {leaving && coming
          ? `${coming.short_name} on for ${leaving.short_name}${dead ? '' : ' at the next stoppage'}`
          : 'Pick a player off and one on'}
      </Button>
      </>)}
      {waiting.map((w) => (
        <Text key={w.out} size="xs" c="orange">
          Waiting for the ball to go out: {nameOf(w.in)} on for {nameOf(w.out)}
        </Text>
      ))}
    </Stack>
  )
}
