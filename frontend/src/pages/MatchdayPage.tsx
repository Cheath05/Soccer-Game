import { Alert, Badge, Button, Card, Group, Stack, Table, Text } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'

import { useCareer, usePlayInstant, useTactics } from '../api/hooks'
import type { ClubRef } from '../api/types'
import { Crest } from '../components/PhoneNav'
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
    <Stack gap="sm">
      <Card className="fs-hero" data-matchday padding="lg">
        <Text className="fs-label" ta="center">
          {fixture.competition_name} · {stageLabel(fixture.stage, fixture.round, fixture.tie, fixture.leg, fixture.stage_name)}
        </Text>
        <Group mt="md" justify="space-between" align="flex-start" wrap="nowrap" gap="xs">
          <Side club={fixture.home} mine={fixture.home.id === career.club.id} />
          <Text className="fs-num" fz={26} c="dimmed" pt={16}>
            V
          </Text>
          <Side club={fixture.away} mine={fixture.away.id === career.club.id} />
        </Group>
        <Text size="sm" c="dimmed" ta="center" mt="md">
          {longDate(fixture.date)} · {fixture.neutral ? 'Neutral venue' : home ? 'Home' : `Away at ${opponent.name}`}
        </Text>
        {fixture.leg1_home !== null && fixture.leg1_away !== null && (
          <Text size="sm" c="dimmed" ta="center">
            First leg: {fixture.away.name} {fixture.leg1_away} – {fixture.leg1_home} {fixture.home.name}
          </Text>
        )}
        <Stack gap="xs" mt="lg">
          <Button fullWidth size="lg" color="teal" onClick={() => void navigate({ to: '/live/$fixtureId', params: { fixtureId: String(fixture.id) } })}>
            Watch match
          </Button>
          <Group grow gap="xs">
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
            <Button size="md" variant="default" onClick={() => void navigate({ to: '/tactics' })}>
              Tactics
            </Button>
          </Group>
        </Stack>
      </Card>
      {play.error && <Alert color="red">{play.error.message}</Alert>}
      {tactics.data && (
        <Card withBorder>
          <Group justify="space-between" mb="xs" align="baseline">
            <Text className="fs-num" fz={20} tt="uppercase">
              Starting XI · {tactics.data.formation}
            </Text>
            <Text size="xs" c="dimmed">
              {tactics.data.instructions.mentality} mentality · {tactics.data.instructions.pressing} pressing
            </Text>
          </Group>
          <Table verticalSpacing={6} withRowBorders={false}>
            <Table.Tbody>
              {tactics.data.starters.map((s) => (
                <Table.Tr key={s.player_id}>
                  <Table.Td w={32} c="dimmed" className="fs-num">
                    {s.number}
                  </Table.Td>
                  <Table.Td w={60}>
                    <Badge size="sm" color={positionColor(s.position)} variant="light">
                      {s.position}
                    </Badge>
                  </Table.Td>
                  <Table.Td>{s.name}</Table.Td>
                  <Table.Td ta="right" className="fs-num" fz={17}>
                    {s.rating}
                  </Table.Td>
                  <Table.Td ta="right" c={s.condition < 80 ? 'red' : 'dimmed'} fz="sm">
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

function Side({ club, mine }: { club: ClubRef; mine: boolean }) {
  return (
    <Stack align="center" gap={8} style={{ flex: 1, minWidth: 0 }}>
      <Crest name={club.name} size={60} mine={mine} />
      <Text className="fs-num" fz={22} lh={1.1} ta="center" tt="uppercase" lineClamp={2}>
        {club.name}
      </Text>
    </Stack>
  )
}
