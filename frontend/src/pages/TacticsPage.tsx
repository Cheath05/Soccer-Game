import { Alert, Badge, Button, Card, Group, Loader, ScrollArea, SegmentedControl, Select, Stack, Table, Text, Title } from '@mantine/core'
import { useEffect, useState } from 'react'

import { useCareer, useSaveTactics, useSquad, useTactics } from '../api/hooks'
import type { SheetEntry, TacticsUpdate } from '../api/types'
import PitchBoard from '../components/PitchBoard'
import { SlotBreakdown } from '../components/SlotBreakdown'
import { positionColor, ratingColor } from '../lib/format'
import { fullLineup, freeBenchPlace, placeOf, swapInto } from '../lib/lineup'
import type { Lineup } from '../lib/lineup'
import { breakdownText, fitColor } from '../lib/slotRating'

const GROUP_OF: Record<string, string> = {
  GK: 'GK', CB: 'CB', LB: 'FB', RB: 'FB', LWB: 'FB', RWB: 'FB', DM: 'DM', CM: 'CM', AM: 'AM',
  LM: 'W', RM: 'W', LW: 'W', RW: 'W', ST: 'ST',
}

export default function TacticsPage() {
  const career = useCareer().data
  const tactics = useTactics()
  const squad = useSquad(career?.club.id)
  const save = useSaveTactics()
  const [selected, setSelected] = useState<string | null>(null)
  const [dragging, setDragging] = useState<number | null>(null)
  const [over, setOver] = useState<string | null>(null) // a list row or list a drag is over
  const [refusal, setRefusal] = useState<string | null>(null)
  const [picked, setPicked] = useState<number | null>(null) // click-to-move: the player waiting for his new place

  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === 'Escape') setPicked(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (tactics.isPending) return <Loader />
  if (!tactics.data) return <Text c="red">{tactics.error?.message}</Text>
  const t = tactics.data
  const formation = t.formations.find((f) => f.key === t.formation) ?? t.formations[0]
  const slot = formation.slots.find((s) => s.id === selected)
  const entry = t.starters.find((s) => s.slot === selected)
  const everyone = new Map([...t.starters, ...t.bench, ...t.reserves].map((e) => [e.player_id, e]))

  const update = (patch: Partial<TacticsUpdate>) =>
    save.mutate({ formation: t.formation, roles: t.roles, lineup: t.lineup, instructions: t.instructions, ...patch })

  /** Save a changed line-up, unless it would put someone who can't play on the pitch or the bench. */
  const apply = (before: Lineup, after: Lineup) => {
    const unfit = Object.entries(after).find(([k, pid]) => before[k] !== pid && everyone.get(pid)?.available === false)
    if (unfit) {
      setRefusal(`${everyone.get(unfit[1])?.name} is injured or suspended and can't be picked.`)
      return
    }
    setRefusal(null)
    update({ lineup: after })
  }

  const assign = (playerId: number) => {
    if (!selected) return
    const before = fullLineup(t)
    apply(before, swapInto(before, playerId, selected))
  }

  const finishDrag = () => {
    setDragging(null)
    setOver(null)
  }

  const moveToSlot = (playerId: number, slotId: string) => {
    const before = fullLineup(t)
    if (before[slotId] === playerId) return
    apply(before, swapInto(before, playerId, slotId))
  }

  /** Two players change places (a reserve who changes places with a starter becomes a starter). */
  const swapPlayers = (movingId: number, targetId: number) => {
    if (movingId === targetId) return
    const before = fullLineup(t)
    const movingAt = placeOf(before, movingId)
    const targetAt = placeOf(before, targetId)
    if (targetAt !== undefined) apply(before, swapInto(before, movingId, targetAt))
    else if (movingAt !== undefined) apply(before, swapInto(before, targetId, movingAt))
  }

  /** A reserve takes a free bench place, if there is one. */
  const moveToBench = (playerId: number) => {
    const before = fullLineup(t)
    const free = freeBenchPlace(before, t.bench_size)
    if (free === undefined) {
      setRefusal('The bench is full: pick one of the substitutes to swap them.')
      return
    }
    if (placeOf(before, playerId) === undefined) apply(before, swapInto(before, playerId, free))
  }

  const dropOnSlot = (slotId: string) => {
    const dragged = dragging
    finishDrag()
    if (dragged != null) moveToSlot(dragged, slotId)
  }

  const dropOnPlayer = (targetId: number) => {
    const dragged = dragging
    finishDrag()
    if (dragged != null) swapPlayers(dragged, targetId)
  }

  const dropOnBench = () => {
    const dragged = dragging
    finishDrag()
    if (dragged != null) moveToBench(dragged)
  }

  /** Click-to-move on a pitch slot: pick the player there, or put the picked player in this slot. */
  const clickSlot = (slotId: string) => {
    const e = t.starters.find((s) => s.slot === slotId)
    setSelected(slotId)
    if (picked != null) {
      if (!(e && e.player_id === picked)) moveToSlot(picked, slotId)
      setPicked(null)
      return
    }
    setPicked(e?.available ? e.player_id : null)
  }

  /** Click-to-move on a list row: pick the player, or swap the picked player with this one. */
  const clickPlayer = (e: SheetEntry, kind: 'xi' | 'bench' | 'reserve') => {
    if (kind === 'xi') setSelected(e.slot)
    if (picked === e.player_id) {
      setPicked(null)
      return
    }
    if (picked != null) {
      swapPlayers(picked, e.player_id)
      setPicked(null)
      return
    }
    setPicked(e.available ? e.player_id : null)
  }

  const players = (squad.data ?? []).map((p) => ({
    value: String(p.id),
    label: `${p.name} · ${p.position} · ${p.overall}${p.injury ? ' (injured)' : p.suspended ? ' (suspended)' : ''}`,
    disabled: !!p.injury || p.suspended > 0,
  }))

  const row = (e: SheetEntry, kind: 'xi' | 'bench' | 'reserve') => {
    const draggable = e.available
    const key = `${kind}-${e.player_id}`
    const target = over === key && dragging != null && dragging !== e.player_id
    const warn = kind === 'xi' ? fitColor(e) : null
    return (
      <Table.Tr
        key={key}
        draggable={draggable}
        title={kind === 'xi' ? breakdownText(e) : undefined}
        onDragStart={(ev: React.DragEvent) => {
          ev.dataTransfer.effectAllowed = 'move'
          ev.dataTransfer.setData('text/plain', String(e.player_id))
          setDragging(e.player_id)
        }}
        onDragEnd={finishDrag}
        onDragOver={(ev: React.DragEvent) => {
          if (dragging == null) return
          ev.preventDefault()
          ev.stopPropagation()
          setOver(key)
        }}
        onDrop={(ev: React.DragEvent) => {
          ev.preventDefault()
          ev.stopPropagation()
          dropOnPlayer(e.player_id)
        }}
        onClick={() => clickPlayer(e, kind)}
        style={{
          cursor: picked != null || !draggable ? 'pointer' : 'grab',
          opacity: draggable ? 1 : 0.55,
          outline: target ? '2px solid var(--mantine-color-yellow-5)' : undefined,
          background:
            e.player_id === picked
              ? 'var(--mantine-color-yellow-light)'
              : kind === 'xi' && e.slot === selected
                ? 'var(--mantine-color-orange-light)'
                : undefined,
          boxShadow: e.player_id === picked ? 'inset 3px 0 0 var(--mantine-color-yellow-6)' : undefined,
        }}
      >
        <Table.Td w={52}>
          <Badge size="sm" color={positionColor(kind === 'xi' ? e.position : e.best_position)} variant={kind === 'xi' ? 'filled' : 'light'} w={44}>
            {kind === 'xi' ? e.position : e.best_position}
          </Badge>
        </Table.Td>
        <Table.Td>
          <Text size="sm" fw={500}>
            {e.name}
            {!e.available && (
              <Text span size="xs" c="red">
                {' '}
                (unavailable)
              </Text>
            )}
          </Text>
          {kind === 'xi' && <SlotBreakdown entry={e} />}
          {kind !== 'xi' && e.positions.length > 1 && (
            <Text size="xs" c="dimmed">
              {e.positions.join(' · ')}
            </Text>
          )}
        </Table.Td>
        <Table.Td ta="right" w={60}>
          {kind === 'xi' ? (
            <Text span fw={700} c={ratingColor(e.rating)} style={warn ? { borderBottom: `2px solid ${warn === 'red' ? '#fa5252' : '#fd7e14'}` } : undefined}>
              {e.rating}
            </Text>
          ) : (
            <Text span fw={700} c={ratingColor(e.overall)}>
              {e.overall}
            </Text>
          )}
        </Table.Td>
        <Table.Td ta="right" w={44}>
          <Text span size="xs" c="dimmed">
            {e.condition}%
          </Text>
        </Table.Td>
      </Table.Tr>
    )
  }

  const list = (entries: SheetEntry[], kind: 'bench' | 'reserve') => (
    <Table verticalSpacing={1}>
      <Table.Tbody>
        {entries.map((e) => row(e, kind))}
        {kind === 'bench' &&
          Array.from({ length: Math.max(0, t.bench_size - entries.length) }, (_, i) => (
            <Table.Tr
              key={`free-${i}`}
              onClick={() => {
                if (picked != null) {
                  moveToBench(picked)
                  setPicked(null)
                }
              }}
              style={{ cursor: picked != null ? 'pointer' : 'default' }}
            >
              <Table.Td colSpan={4}>
                <Text size="xs" c="dimmed">
                  Empty place{picked != null ? ': click to move him here' : ''}
                </Text>
              </Table.Td>
            </Table.Tr>
          ))}
      </Table.Tbody>
    </Table>
  )

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Tactics</Title>
        <Group>
          <Select
            data={t.formations.map((f) => ({ value: f.key, label: f.name }))}
            value={t.formation}
            onChange={(v) => v && update({ formation: v, roles: {}, lineup: null })}
            allowDeselect={false}
            w={220}
          />
          <Button variant="default" onClick={() => update({ lineup: null })}>
            Pick best XI and bench
          </Button>
        </Group>
      </Group>
      {save.error && <Alert color="red">{save.error.message}</Alert>}
      {refusal && (
        <Alert color="orange" withCloseButton onClose={() => setRefusal(null)}>
          {refusal}
        </Alert>
      )}
      {picked != null && (
        <Alert color="yellow" py={6} withCloseButton onClose={() => setPicked(null)} closeButtonLabel="Cancel move">
          Moving {everyone.get(picked)?.name}: click a position on the pitch, a substitute or a reserve to swap him there. Esc or
          clicking him again cancels.
        </Alert>
      )}
      <Group align="start" gap="lg" wrap="wrap">
        <Stack gap={4}>
          <PitchBoard
            formation={formation}
            starters={t.starters}
            selected={selected}
            onSelect={clickSlot}
            picked={picked}
            dragging={dragging}
            onDragPlayer={setDragging}
            onDropOnSlot={dropOnSlot}
          />
          <Text size="xs" c="dimmed" maw={340}>
            Click a player, then click where he should go (or drag him there). The number is his rating in that position; a ring
            marks a player who is not fully at home there (amber a little, red out of position).
          </Text>
        </Stack>
        <Stack gap="xs" style={{ flex: '0 1 300px', minWidth: 280 }}>
          <Card
            withBorder
            p="xs"
            onDragOver={(ev: React.DragEvent) => {
              if (dragging == null) return
              ev.preventDefault()
              setOver('bench')
            }}
            onDrop={(ev: React.DragEvent) => {
              ev.preventDefault()
              dropOnBench()
            }}
            style={over === 'bench' && dragging != null ? { outline: '2px dashed var(--mantine-color-yellow-5)' } : undefined}
          >
            <Text fw={600} size="sm" mb={2}>
              Bench ({t.bench.length}/{t.bench_size}) {t.bench_chosen ? '' : '(auto)'}
            </Text>
            {list(t.bench, 'bench')}
          </Card>
          <Card withBorder p="xs">
            <Text fw={600} size="sm" mb={2}>
              Reserves ({t.reserves.length})
            </Text>
            <ScrollArea.Autosize mah={320}>{list(t.reserves, 'reserve')}</ScrollArea.Autosize>
          </Card>
        </Stack>
        <Stack style={{ flex: '1 1 320px', minWidth: 300 }}>
          <Card withBorder>
            {slot && entry ? (
              <Stack gap="xs">
                <Group justify="space-between">
                  <Text fw={600}>
                    {slot.id} · {entry.name}
                  </Text>
                  <Badge color={positionColor(slot.position)}>{slot.position}</Badge>
                </Group>
                <Select
                  label="Player"
                  searchable
                  data={players}
                  value={String(entry.player_id)}
                  onChange={(v) => v && assign(Number(v))}
                  allowDeselect={false}
                />
                <Select
                  label="Role"
                  data={(t.roles_by_group[GROUP_OF[slot.position]] ?? []).map((r) => ({ value: r.key, label: r.name }))}
                  value={t.roles[slot.id] ?? slot.default_role}
                  onChange={(v) => v && update({ roles: { ...t.roles, [slot.id]: v } })}
                  allowDeselect={false}
                />
                <Text size="xs" c="dimmed">
                  {t.roles_by_group[GROUP_OF[slot.position]]?.find((r) => r.key === (t.roles[slot.id] ?? slot.default_role))?.description}
                </Text>
              </Stack>
            ) : (
              <Text c="dimmed" size="sm">
                Click a player on the board to change who plays there and their role.
              </Text>
            )}
          </Card>
          <Card withBorder>
            <Group justify="space-between" mb="xs">
              <Text fw={600}>Starting XI</Text>
              <Text size="xs" c="dimmed">
                Rating in the position, and why it differs from his overall
              </Text>
            </Group>
            <Table verticalSpacing={2}>
              <Table.Tbody>{t.starters.map((s) => row(s, 'xi'))}</Table.Tbody>
            </Table>
          </Card>
          <Card withBorder>
            <Text fw={600} mb="xs">
              Team instructions
            </Text>
            <Stack gap="xs">
              {t.instruction_options.map((ins) => (
                <Group key={ins.key} justify="space-between" wrap="nowrap">
                  <Text size="sm" w={120}>
                    {ins.label}
                  </Text>
                  <SegmentedControl
                    size="xs"
                    value={t.instructions[ins.key] ?? ins.default}
                    onChange={(v) => update({ instructions: { ...t.instructions, [ins.key]: v } })}
                    data={ins.options.map((o) => ({ value: o, label: o }))}
                  />
                </Group>
              ))}
            </Stack>
          </Card>
        </Stack>
      </Group>
      {save.isPending && <Loader size="sm" />}
    </Stack>
  )
}
