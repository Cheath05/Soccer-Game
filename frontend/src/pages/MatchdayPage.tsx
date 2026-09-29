import { Alert, Badge, Button, Card, Group, Stack, Table, Text, Title } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'

import { useCareer, usePlayInstant, useTactics } from '../api/hooks'
import ClubLink from '../components/ClubLink'
import { longDate, positionColor, stageLabel } from '../lib/format'

export default function MatchdayPage() {
  const career = useCareer().data
  const tactics = useTactics()
  const play = usePlayInstant()
  const navigate = useNavigate()
  if (!career) return null
  const fixture = career.next_fixture
  if (!fixture || fixture.date !== career.date) {
    return <Text>No match today. Press Continue to advance to the next match day.</Text>
  }
  const home = fixture.home.id === career.club.id
  const opponent = home ? fixture.away : fixture.home

  return (
    <Stack>
      <Title order={2}>Match day</Title>
      <Card withBorder>
        <Stack gap={4} align="center">
          <Text c="dimmed" size="sm">
            {fixture.competition_name} · {stageLabel(fixture.stage, fixture.round, fixture.tie, fixture.leg)} · {longDate(fixture.date)}
          </Text>
          <Title order={2}>
            <ClubLink club={fixture.home} /> v <ClubLink club={fixture.away} />
          </Title>
          <Text size="sm">{fixture.neutral ? 'Neutral venue' : home ? 'Home' : `Away at ${opponent.name}`}</Text>
          <Group mt="md">
            <Button size="md" color="teal" onClick={() => void navigate({ to: '/live/$fixtureId', params: { fixtureId: String(fixture.id) } })}>
              Watch match
            </Button>
            <Button
              size="md"
              variant="default"
              loading={play.isPending}
              onClick={() =>
                play.mutate(fixture.id, {
                  onSuccess: () => void navigate({ to: '/match/$fixtureId', params: { fixtureId: String(fixture.id) } }),
                })
              }
            >
              Instant result
            </Button>
            <Button size="md" variant="subtle" onClick={() => void navigate({ to: '/tactics' })}>
              Tactics
            </Button>
          </Group>
        </Stack>
      </Card>
      {play.error && <Alert color="red">{play.error.message}</Alert>}
      {tactics.data && (
        <Card withBorder>
          <Group justify="space-between" mb="xs">
            <Text fw={600}>Your starting XI ({tactics.data.formation})</Text>
            <Text size="sm" c="dimmed">
              {tactics.data.instructions.mentality} mentality · {tactics.data.instructions.pressing} pressing
            </Text>
          </Group>
          <Table verticalSpacing={2}>
            <Table.Tbody>
              {tactics.data.starters.map((s) => (
                <Table.Tr key={s.player_id}>
                  <Table.Td w={36}>{s.number}</Table.Td>
                  <Table.Td w={60}>
                    <Badge size="sm" color={positionColor(s.position)} variant="light">
                      {s.position}
                    </Badge>
                  </Table.Td>
                  <Table.Td>{s.name}</Table.Td>
                  <Table.Td ta="right">{s.rating}</Table.Td>
                  <Table.Td ta="right" c={s.condition < 80 ? 'red' : undefined}>
                    {s.condition}%
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Card>
      )}
    </Stack>
  )
}
