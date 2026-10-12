import { Box, Button, Group, Modal, Paper, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import { useState } from 'react'

import StatsPanel from './StatsPanel'
import type { LiveMatch } from './useLiveMatch'

// Shown over the pitch at half-time (and the breaks around extra time). Changes made in the
// Tactics and Subs tabs now take effect when the next period starts.
export default function HalfTimePanel({ match, sheet = false }: { match: LiveMatch; sheet?: boolean }) {
  const { live, send } = match
  const [away, setAway] = useState(false) // phone: the sheet is put aside to use the tabs
  if (!live) return null
  const next = live.clock.period === 1 ? 'Start second half' : live.clock.period === 2 ? 'Start extra time' : 'Start second half of extra time'
  const mine = live.status.players.filter((p) => p.team === live.userTeam && p.active)
  const tired = [...mine].sort((a, b) => a.energy - b.energy).slice(0, 3)
  const best = [...mine].sort((a, b) => b.rating - a.rating).slice(0, 3)
  const body = (
    <Stack gap="sm">
      <Group justify="space-between">
        <Title order={3}>{live.clock.period === 1 ? 'Half-time' : 'Break'}</Title>
        <Title order={3}>
          {live.score[0]} – {live.score[1]}
        </Title>
      </Group>
      <StatsPanel stats={live.stats} />
      <SimpleGrid cols={2}>
        <Stack gap={2}>
          <Text size="xs" c="dimmed">
            Most tired
          </Text>
          {tired.map((p) => (
            <Text key={p.player_id} size="sm">
              {p.short_name} · {p.energy}%
            </Text>
          ))}
        </Stack>
        <Stack gap={2}>
          <Text size="xs" c="dimmed">
            Best rated
          </Text>
          {best.map((p) => (
            <Text key={p.player_id} size="sm">
              {p.short_name} · {p.rating.toFixed(1)}
            </Text>
          ))}
        </Stack>
      </SimpleGrid>
      <Text size="xs" c="dimmed">
        Make any changes in the Tactics and Subs tabs before the restart.
      </Text>
      {sheet && (
        <Button variant="default" radius="xl" h={44} onClick={() => setAway(true)}>
          Tactics and substitutions
        </Button>
      )}
      <Button color="teal" radius="xl" h={sheet ? 44 : undefined} onClick={() => send({ type: 'start_period' })}>
        {next}
      </Button>
    </Stack>
  )
  if (sheet) {
    // Phone: a full-screen sheet; "Tactics and substitutions" puts it aside, leaving a bar to
    // bring it back or restart.
    return (
      <>
        <Modal opened={!away} onClose={() => setAway(true)} fullScreen withCloseButton={false} zIndex={300} title={undefined}>
          {body}
        </Modal>
        {away && (
          <Box
            style={{
              position: 'fixed',
              left: 0,
              right: 0,
              bottom: 0,
              zIndex: 250,
              padding: 8,
              display: 'flex',
              gap: 8,
              background: 'var(--mantine-color-body)',
              borderTop: '1px solid var(--mantine-color-default-border)',
            }}
          >
            <Button variant="default" radius="xl" h={44} style={{ flex: 1 }} onClick={() => setAway(false)}>
              Half-time summary
            </Button>
            <Button color="teal" radius="xl" h={44} style={{ flex: 1 }} onClick={() => send({ type: 'start_period' })}>
              {next}
            </Button>
          </Box>
        )}
      </>
    )
  }
  return (
    <Paper
      shadow="xl"
      p="md"
      radius="lg"
      withBorder
      w={460}
      maw="94%"
      mah="96%"
      style={{ overflowY: 'auto', backdropFilter: 'blur(12px)', background: 'color-mix(in srgb, var(--mantine-color-body) 90%, transparent)' }}
    >
      {body}
    </Paper>
  )
}
