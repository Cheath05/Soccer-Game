import { Alert, Badge, Button, Card, Container, Group, Loader, SegmentedControl, Select, SimpleGrid, Stack, Text, TextInput, Title, UnstyledButton } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import { useLoadCareer, useNewCareer, useSaves, useWorldLeagues } from '../api/hooks'
import { longDate } from '../lib/format'

export default function StartPage({ hasCareer, error }: { hasCareer: boolean; error: Error | null }) {
  const saves = useSaves()
  const leagues = useWorldLeagues()
  const newCareer = useNewCareer()
  const loadCareer = useLoadCareer()
  const navigate = useNavigate()
  const [manager, setManager] = useState('')
  const [league, setLeague] = useState('ENG1')
  const [clubId, setClubId] = useState<number | null>(null)
  const [slot, setSlot] = useState('1')

  const selectedLeague = leagues.data?.find((l) => l.key === league)
  const slotInfo = saves.data?.find((s) => String(s.slot) === slot)
  const goHome = () => void navigate({ to: '/' })

  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        <Group justify="space-between">
          <div>
            <Title order={1}>Footsim</Title>
            <Text c="dimmed">A football management simulation.</Text>
          </div>
          {hasCareer && (
            <Button variant="default" onClick={goHome}>
              Back to career
            </Button>
          )}
        </Group>
        {error && <Alert color="red">{error.message}</Alert>}

        <Stack gap="sm">
          <Title order={3}>Saved careers</Title>
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            {(saves.data ?? []).map((s) => (
              <Card key={s.slot} withBorder>
                <Group justify="space-between" mb="xs">
                  <Text fw={600}>Slot {s.slot}</Text>
                  {s.active && <Badge color="teal">Playing</Badge>}
                </Group>
                {s.has_save || s.has_autosave ? (
                  <Stack gap={4}>
                    <Text>{s.club ?? 'Career'}</Text>
                    <Text size="sm" c="dimmed">
                      {s.manager ?? ''} {s.game_date ? `· ${longDate(s.game_date)}` : ''}
                    </Text>
                    <Group gap="xs" mt="xs">
                      {s.has_save && (
                        <Button size="xs" loading={loadCareer.isPending} onClick={() => loadCareer.mutate({ slot: s.slot }, { onSuccess: goHome })}>
                          Load
                        </Button>
                      )}
                      {s.has_autosave && (
                        <Button size="xs" variant="default" onClick={() => loadCareer.mutate({ slot: s.slot, autosave: true }, { onSuccess: goHome })}>
                          Load autosave
                        </Button>
                      )}
                    </Group>
                  </Stack>
                ) : (
                  <Text c="dimmed" size="sm">
                    Empty
                  </Text>
                )}
              </Card>
            ))}
          </SimpleGrid>
          {loadCareer.error && <Alert color="red">{loadCareer.error.message}</Alert>}
        </Stack>

        <Stack gap="sm">
          <Title order={3}>New career</Title>
          <Group align="end">
            <TextInput label="Manager name" placeholder="Your name" value={manager} onChange={(e) => setManager(e.currentTarget.value)} />
            <Select label="Save slot" data={['1', '2', '3']} value={slot} onChange={(v) => setSlot(v ?? '1')} w={110} allowDeselect={false} />
          </Group>
          {leagues.isPending && <Loader />}
          {leagues.error && <Alert color="red">{leagues.error.message}</Alert>}
          {leagues.data && (
            <>
              <SegmentedControl
                value={league}
                onChange={(v) => {
                  setLeague(v)
                  setClubId(null)
                }}
                data={leagues.data.map((l) => ({ value: l.key, label: l.name }))}
              />
              <SimpleGrid cols={{ base: 2, sm: 3, md: 4 }} spacing="xs">
                {selectedLeague?.clubs.map((c) => (
                  <UnstyledButton key={c.id} onClick={() => setClubId(c.id)}>
                    <Card withBorder padding="sm" bg={clubId === c.id ? 'var(--mantine-color-teal-light)' : undefined}>
                      <Text fw={600} truncate>
                        {c.name}
                      </Text>
                      <Text size="xs" c="dimmed">
                        Squad {c.average_overall.toFixed(1)} · Reputation {c.reputation}
                      </Text>
                    </Card>
                  </UnstyledButton>
                ))}
              </SimpleGrid>
            </>
          )}
          {slotInfo?.has_save && <Alert color="yellow">Slot {slot} already has a career. Starting a new one replaces it.</Alert>}
          {newCareer.error && <Alert color="red">{newCareer.error.message}</Alert>}
          <Group>
            <Button
              size="md"
              disabled={clubId === null}
              loading={newCareer.isPending}
              onClick={() => clubId !== null && newCareer.mutate({ slot: Number(slot), clubId, manager: manager || 'Manager' }, { onSuccess: goHome })}
            >
              Start career
            </Button>
          </Group>
        </Stack>
      </Stack>
    </Container>
  )
}
