import { Badge, Button, Card, Grid, Group, Loader, Modal, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core'
import { useParams } from '@tanstack/react-router'
import { useState } from 'react'

import { usePlayer, useReleasePlayer } from '../api/hooks'
import ClubLink from '../components/ClubLink'
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
            {p.age} years · {p.nationality ?? 'Unknown'} · {p.club ? <ClubLink club={p.club} /> : p.retired ? 'Retired' : 'Free agent'}
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
          {p.own_player && <ReleaseButton playerId={p.id} name={p.name} />}
          <Card withBorder padding="sm" ta="center" miw={90}>
            <Text size="xs" c="dimmed">
              Overall
            </Text>
            <Text fz={32} fw={800} c={ratingColor(p.overall)}>
              {p.overall}
            </Text>
            {!!p.trend && (
              <Text size="xs" fw={600} c={p.trend > 0 ? 'green.7' : 'red.7'}>
                {p.trend > 0 ? '▲ Rising lately' : '▼ Falling lately'}
              </Text>
            )}
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

      <Stack gap={4}>
        <SimpleGrid cols={{ base: 3, sm: 6 }}>
          {Object.entries(p.face).map(([k, v]) => {
            const key = (p.face_key ?? []).includes(k)
            return (
              <Card
                key={k}
                withBorder
                padding="xs"
                ta="center"
                style={key ? { borderColor: 'var(--mantine-primary-color-filled)' } : undefined}
              >
                <Text size="xs" c={key ? undefined : 'dimmed'} fw={key ? 700 : undefined}>
                  {k}
                </Text>
                <Text fw={700} fz="xl" c={ratingColor(v)}>
                  {v}
                </Text>
              </Card>
            )
          })}
        </SimpleGrid>
        <Text size="xs" c="dimmed">
          Outlined: the ratings that count most towards a {p.position}&apos;s overall. Every one of them counts
          for something.
        </Text>
      </Stack>

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
                  {p.wage_weekly_eur !== null && <Row label="Wage" value={wage(p.wage_weekly_eur)} />}
                  <Row label="Contract" value={`until ${p.contract_end}`} />
                  {p.condition !== null && <Row label="Condition" value={`${p.condition}%`} />}
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

function ReleaseButton({ playerId, name }: { playerId: number; name: string }) {
  const [opened, setOpened] = useState(false)
  const release = useReleasePlayer()
  return (
    <>
      <Button variant="subtle" color="red" size="xs" onClick={() => setOpened(true)}>
        Release
      </Button>
      <Modal opened={opened} onClose={() => setOpened(false)} title={`Release ${name}?`} centered>
        <Stack>
          <Text size="sm">His contract ends today and he leaves as a free agent. Until transfers are in the game, a released player isn&apos;t signed by anyone, and most leave the professional game at the end of the season.</Text>
          {release.error && (
            <Text c="red" size="sm">
              {release.error.message}
            </Text>
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setOpened(false)}>
              Keep him
            </Button>
            <Button color="red" loading={release.isPending} onClick={() => release.mutate(playerId, { onSuccess: () => setOpened(false) })}>
              Release
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  )
}
