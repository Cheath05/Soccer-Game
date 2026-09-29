import { Box, CloseButton, Group, Paper, Progress, SimpleGrid, Stack, Text } from '@mantine/core'

import { TEAM_COLORS } from './draw'
import type { PlayerStatus } from './protocol'
import { MatchRating, Ovr } from './SubsPanel'

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <Stack gap={0} align="center">
      <Text size="sm" fw={700}>
        {value}
      </Text>
      <Text size="10px" c="dimmed" tt="uppercase">
        {label}
      </Text>
    </Stack>
  )
}

// A compact card for the player clicked on the pitch; small enough to leave the play visible.
export default function PlayerCard({ player, onClose }: { player: PlayerStatus; onClose: () => void }) {
  const keeper = player.position === 'GK'
  return (
    <Paper shadow="md" p="xs" radius="md" withBorder w={270} style={{ opacity: 0.96 }}>
      <Group justify="space-between" wrap="nowrap" mb={4}>
        <Group gap={6} wrap="nowrap">
          <Box w={10} h={10} style={{ background: TEAM_COLORS[player.team].shirt, borderRadius: 2 }} />
          <Text fw={700} size="sm" lineClamp={1}>
            {player.number}. {player.name}
          </Text>
        </Group>
        <CloseButton size="sm" onClick={onClose} />
      </Group>
      <Group justify="space-between" mb={6}>
        <Text size="xs" c="dimmed">
          {player.position} · {player.role}
        </Text>
        <Group gap={6}>
          <Ovr value={player.ovr} />
          <MatchRating value={player.rating} />
          {player.red ? '🟥' : player.yellow ? '🟨' : null}
        </Group>
      </Group>
      <Group gap="xs" grow mb={6}>
        <Stack gap={2}>
          <Text size="10px" c="dimmed">
            Energy {player.energy}%
          </Text>
          <Progress value={player.energy} size="xs" color={player.energy > 75 ? 'teal' : player.energy > 60 ? 'yellow' : 'red'} />
        </Stack>
        <Stack gap={2}>
          <Text size="10px" c="dimmed">
            Fitness at kick-off {player.condition}%
          </Text>
          <Progress value={player.condition} size="xs" color="gray" />
        </Stack>
      </Group>
      <SimpleGrid cols={5} spacing={4} verticalSpacing={4}>
        <Stat label="Goals" value={player.goals} />
        <Stat label="Assists" value={player.assists} />
        <Stat label="Shots" value={`${player.on_target}/${player.shots}`} />
        <Stat label="xG" value={player.xg.toFixed(2)} />
        <Stat label="Pass %" value={player.pass_pct ?? '–'} />
        <Stat label="Passes" value={player.passes} />
        <Stat label="Tkl" value={player.tackles} />
        <Stat label="Int" value={player.interceptions} />
        <Stat label="Fouls" value={player.fouls} />
        {keeper ? <Stat label="Saves" value={player.saves} /> : <Stat label="Mins" value={player.minutes} />}
      </SimpleGrid>
    </Paper>
  )
}
