import { Badge, Card, Grid, Group, Loader, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core'
import { useParams } from '@tanstack/react-router'

import { usePlayer } from '../api/hooks'
import { attributeLabel, money, positionColor, ratingColor, wage } from '../lib/format'

const GROUP_TITLES: Record<string, string> = {
  technical: 'Technical',
  mental: 'Mental',
  physical: 'Physical',
  defensive: 'Defending',
  goalkeeping: 'Goalkeeping',
}

export default function PlayerPage() {
  const { playerId } = useParams({ from: '/players/$playerId' })
  const player = usePlayer(Number(playerId))
  if (player.isPending) return <Loader />
  if (!player.data) return <Text c="red">{player.error?.message}</Text>
  const p = player.data
  const keeper = p.position === 'GK'
  const groups = keeper
    ? ['goalkeeping', 'physical', 'mental', 'technical']
    : ['technical', 'mental', 'physical', 'defensive']

  return (
    <Stack>
      <Group justify="space-between" align="start">
        <div>
          <Title order={2}>{p.name}</Title>
          <Text c="dimmed">
            {p.age} years · {p.nationality ?? 'Unknown'} · {p.club?.name ?? 'Free agent'}
          </Text>
          <Group gap={6} mt={6}>
            {Object.entries(p.familiarity)
              .filter(([, f]) => f >= 15)
              .sort((a, b) => b[1] - a[1])
              .map(([pos]) => (
                <Badge key={pos} color={positionColor(pos)} variant={pos === p.position ? 'filled' : 'light'}>
                  {pos}
                </Badge>
              ))}
          </Group>
        </div>
        <Group>
          <Card withBorder padding="sm" ta="center" miw={90}>
            <Text size="xs" c="dimmed">
              Overall
            </Text>
            <Text fz={32} fw={800} c={ratingColor(p.overall)}>
              {p.overall}
            </Text>
          </Card>
          <Card withBorder padding="sm" ta="center" miw={150}>
            <Text size="xs" c="dimmed">
              Potential (scouted)
            </Text>
            <Text fz={22} fw={700}>
              {p.potential.low === p.potential.high ? p.potential.low : `${p.potential.low}–${p.potential.high}`}
            </Text>
            <Text size="xs">{p.potential.label}</Text>
          </Card>
        </Group>
      </Group>

      <SimpleGrid cols={{ base: 3, sm: 6 }}>
        {Object.entries(p.face).map(([k, v]) => (
          <Card key={k} withBorder padding="xs" ta="center">
            <Text size="xs" c="dimmed">
              {k}
            </Text>
            <Text fw={700} fz="xl" c={ratingColor(v)}>
              {v}
            </Text>
          </Card>
        ))}
      </SimpleGrid>

      <Grid>
        <Grid.Col span={{ base: 12, md: 8 }}>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            {groups.map((g) => (
              <Card key={g} withBorder padding="sm">
                <Text fw={600} mb={4}>
                  {GROUP_TITLES[g]}
                </Text>
                {(p.attributes[g] ?? []).map((a) => (
                  <Group key={a.key} justify="space-between" gap={4}>
                    <Text size="sm">{attributeLabel(a.key)}</Text>
                    <Text size="sm" fw={700} c={ratingColor(a.value)}>
                      {a.value}
                    </Text>
                  </Group>
                ))}
              </Card>
            ))}
          </SimpleGrid>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Stack>
            <Card withBorder padding="sm">
              <Text fw={600} mb={4}>
                Best roles
              </Text>
              {p.roles.map((r) => (
                <Group key={r.key} justify="space-between">
                  <Text size="sm">{r.name}</Text>
                  <Text size="sm" fw={700} c={ratingColor(r.rating)}>
                    {r.rating}
                  </Text>
                </Group>
              ))}
            </Card>
            <Card withBorder padding="sm">
              <Text fw={600} mb={4}>
                Details
              </Text>
              <Table verticalSpacing={2}>
                <Table.Tbody>
                  <Row label="Height" value={p.height_cm ? `${p.height_cm} cm` : '–'} />
                  <Row label="Weight" value={p.weight_kg ? `${p.weight_kg} kg` : '–'} />
                  <Row label="Foot" value={`${p.preferred_foot} (weak foot ${p.weak_foot}★)`} />
                  <Row label="Skill moves" value={`${p.skill_moves}★`} />
                  <Row label="Value" value={money(p.value_eur)} />
                  <Row label="Wage" value={wage(p.wage_weekly_eur)} />
                  <Row label="Contract" value={`until ${p.contract_end}`} />
                  <Row label="Condition" value={`${p.condition}%`} />
                  <Row label="Season" value={`${p.appearances} apps · ${p.goals} goals · ${p.assists} assists`} />
                  {p.average_rating !== null && <Row label="Avg rating" value={p.average_rating.toFixed(2)} />}
                </Table.Tbody>
              </Table>
            </Card>
            {p.traits.length > 0 && (
              <Card withBorder padding="sm">
                <Text fw={600} mb={4}>
                  Traits
                </Text>
                <Group gap={6}>
                  {p.traits.map((t) => (
                    <Badge key={t} variant="outline">
                      {t.replaceAll('_', ' ')}
                    </Badge>
                  ))}
                </Group>
              </Card>
            )}
          </Stack>
        </Grid.Col>
      </Grid>
    </Stack>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <Table.Tr>
      <Table.Td c="dimmed">{label}</Table.Td>
      <Table.Td>{value}</Table.Td>
    </Table.Tr>
  )
}
