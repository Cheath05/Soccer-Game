import { Box, Button, Group, Select, Stack, Text } from '@mantine/core'

import type { PendingSub, PlayerStatus, RoleOption } from './protocol'
import type { LiveMatch } from './useLiveMatch'

/** A small booked or sent-off card: yellow for a booking, red once he is off. Nothing if he is clean. */
export function CardIcon({ player }: { player: Pick<PlayerStatus, 'yellow' | 'red'> }) {
  if (!player.red && !player.yellow) return null
  const red = player.red
  return (
    <Box
      component="span"
      title={red ? 'Sent off' : player.yellow > 1 ? `${player.yellow} yellow cards` : 'Booked (yellow card)'}
      style={{
        display: 'inline-block',
        width: 8,
        height: 11,
        borderRadius: 1.5,
        background: red ? '#e03131' : '#fcc419',
        border: '1px solid rgba(0,0,0,0.45)',
        verticalAlign: 'middle',
      }}
    />
  )
}

function roleOptions(roles: RoleOption[]) {
  return roles.map((r) => ({ value: r.key, label: `${r.name} · ${r.ovr}` }))
}

/** Picks the role of a player; ``current`` is a role key. */
export function RoleSelect({
  roles,
  current,
  onChange,
  label,
  w,
}: {
  roles: RoleOption[]
  current: string | null | undefined
  onChange: (key: string) => void
  label?: string
  w?: number | string
}) {
  return (
    <Select
      size="xs"
      label={label}
      aria-label={label ?? 'Role'}
      w={w}
      data={roleOptions(roles)}
      value={current ?? null}
      onChange={(v) => v && v !== current && onChange(v)}
      allowDeselect={false}
      comboboxProps={{ withinPortal: true }}
      onClick={(e) => e.stopPropagation()}
    />
  )
}

/** Substitutions waiting (staged while paused, or for the next stoppage): the newcomer's role, and Undo. */
export function PendingSubs({ match, nameOf }: { match: LiveMatch; nameOf: (id: number) => string }) {
  const { live, send } = match
  if (!live) return null
  const waiting: PendingSub[] = live.pendingSubs?.[live.userTeam] ?? []
  if (!waiting.length) return null
  return (
    <Stack gap={6}>
      {waiting.map((w) => (
        <Box key={`${w.out}-${w.in}`} p={6} style={{ border: '1px solid var(--mantine-color-orange-6)', borderRadius: 6 }}>
          <Group justify="space-between" wrap="nowrap" gap="xs">
            <Text size="xs" c="orange" fw={600}>
              Waiting: {nameOf(w.out)} ⇄ {nameOf(w.in)}, {w.staged ? 'made when play resumes' : 'made at the next stoppage'}
            </Text>
            <Button size="compact-xs" variant="default" onClick={() => send({ type: 'cancel_sub', out: w.out })}>
              Undo
            </Button>
          </Group>
          {w.roles && w.roles.length > 0 && (
            <RoleSelect
              label={`${nameOf(w.in)}'s role`}
              roles={w.roles}
              current={w.role}
              onChange={(key) => send({ type: 'role', player: w.in, role: key })}
            />
          )}
        </Box>
      ))}
    </Stack>
  )
}
