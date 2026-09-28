import { Alert, Badge, Button, Card, Group, Loader, SegmentedControl, Select, Stack, Table, Text, Title } from '@mantine/core'
import { useState } from 'react'

import { useCareer, useSaveTactics, useSquad, useTactics } from '../api/hooks'
import type { Tactics, TacticsUpdate } from '../api/types'
import PitchBoard from '../components/PitchBoard'
import { positionColor } from '../lib/format'

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

  if (tactics.isPending) return <Loader />
  if (!tactics.data) return <Text c="red">{tactics.error?.message}</Text>
  const t = tactics.data
  const formation = t.formations.find((f) => f.key === t.formation) ?? t.formations[0]
  const slot = formation.slots.find((s) => s.id === selected)
  const entry = t.starters.find((s) => s.slot === selected)

  const update = (patch: Partial<TacticsUpdate>) =>
    save.mutate({ formation: t.formation, roles: t.roles, lineup: t.lineup, instructions: t.instructions, ...patch })

  const currentLineup = (tt: Tactics) => Object.fromEntries(tt.starters.map((s) => [s.slot as string, s.player_id]))

  const assign = (playerId: number) => {
    if (!selected) return
    const lineup = currentLineup(t)
    const previousSlot = Object.entries(lineup).find(([, pid]) => pid === playerId)?.[0]
    const displaced = lineup[selected]
    lineup[selected] = playerId
    if (previousSlot && previousSlot !== selected) lineup[previousSlot] = displaced
    update({ lineup })
  }

  const players = (squad.data ?? []).map((p) => ({
    value: String(p.id),
    label: `${p.name} · ${p.position} · ${p.overall}${p.injury ? ' (injured)' : p.suspended ? ' (suspended)' : ''}`,
    disabled: !!p.injury || p.suspended > 0,
  }))

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
            Pick best XI
          </Button>
        </Group>
      </Group>
      {save.error && <Alert color="red">{save.error.message}</Alert>}
      <Group align="start" gap="lg" wrap="wrap">
        <PitchBoard formation={formation} starters={t.starters} selected={selected} onSelect={setSelected} />
        <Stack style={{ flex: 1, minWidth: 300 }}>
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
          <Card withBorder>
            <Text fw={600} mb="xs">
              Bench {t.lineup ? '' : '(picked automatically)'}
            </Text>
            <Table verticalSpacing={2}>
              <Table.Tbody>
                {t.bench.map((b) => (
                  <Table.Tr key={b.player_id}>
                    <Table.Td w={36}>{b.number}</Table.Td>
                    <Table.Td>{b.name}</Table.Td>
                    <Table.Td>
                      <Badge size="sm" color={positionColor(b.position)} variant="light">
                        {b.position}
                      </Badge>
                    </Table.Td>
                    <Table.Td ta="right">{b.rating}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Card>
        </Stack>
      </Group>
      {save.isPending && <Loader size="sm" />}
    </Stack>
  )
}
