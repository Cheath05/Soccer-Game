import { Alert, Badge, Button, Card, Container, Group, Loader, NumberInput, SegmentedControl, Select, SimpleGrid, Stack, Switch, Text, TextInput, Title, UnstyledButton } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import { useLoadCareer, useNewCareer, useSaves, useWorldLeagues } from '../api/hooks'
import LeaguePicker from '../components/LeaguePicker'
import VersionTag from '../components/VersionTag'
import { CURRENCIES, type Currency, longDate, setCurrency, toEuros, useCurrency } from '../lib/format'

const MAX_BUDGET_EUR = 10_000_000_000 // the most the sandbox gives (the server's limit)

export default function StartPage({ hasCareer, error }: { hasCareer: boolean; error: Error | null }) {
  const saves = useSaves()
  const leagues = useWorldLeagues()
  const newCareer = useNewCareer()
  const loadCareer = useLoadCareer()
  const navigate = useNavigate()
  const currency = useCurrency()
  const [manager, setManager] = useState('')
  // The sandbox budget, typed in millions of the money shown (dollars unless changed here).
  const [budgetMillions, setBudgetMillions] = useState<number | string>('')
  const [board, setBoard] = useState(true)
  const [boardTouched, setBoardTouched] = useState(false)
  const [league, setLeague] = useState('ENG1')
  const [clubId, setClubId] = useState<number | null>(null)
  const [slot, setSlot] = useState('1')

  const selectedLeague = leagues.data?.find((l) => l.key === league)
  const slotInfo = saves.data?.find((s) => String(s.slot) === slot)
  // Go home once a career is started or loaded. Awaited on the mutation itself, not via
  // mutate's onSuccess: the refetch that follows can unmount this page (the layout shows a
  // loader while the career query reloads), and TanStack Query then drops that callback,
  // leaving /start on screen. Errors are shown from the mutation's own state.
  const goHome = () => void navigate({ to: '/' })
  const ignore = () => undefined

  return (
    <Container size="lg" py="xl">
      <Stack gap="xl">
        <Group justify="space-between">
          <div>
            <Title order={1}>Footsim</Title>
            <Text c="dimmed">A football management simulation.</Text>
            <VersionTag />
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
                        <Button size="xs" loading={loadCareer.isPending} onClick={() => void loadCareer.mutateAsync({ slot: s.slot }).then(goHome, ignore)}>
                          Load
                        </Button>
                      )}
                      {s.has_autosave && (
                        <Button size="xs" variant="default" onClick={() => void loadCareer.mutateAsync({ slot: s.slot, autosave: true }).then(goHome, ignore)}>
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
            <NumberInput
              label={`Sandbox: budget (${CURRENCIES[currency].symbol}M)`}
              description="Optional. To spend on transfer fees and wages. Leave empty for the board's budget"
              placeholder="Board's budget"
              min={0}
              max={Math.floor((MAX_BUDGET_EUR / 1_000_000) * CURRENCIES[currency].perEuro)}
              thousandSeparator=","
              value={budgetMillions}
              onChange={(v) => {
                setBudgetMillions(v)
                // A sandbox is for fun: no board unless asked for (it would trim the budget each season).
                if (!boardTouched) setBoard(v === '')
              }}
              w={300}
            />
            <SegmentedControl
              size="xs"
              value={currency}
              onChange={(v) => setCurrency(v as Currency)}
              data={(Object.keys(CURRENCIES) as Currency[]).map((c) => ({ value: c, label: CURRENCIES[c].label }))}
            />
          </Group>
          <Switch
            label="Board expectations"
            description="Off means no targets and no sacking, and your budget is all your cash."
            checked={board}
            onChange={(e) => {
              setBoardTouched(true)
              setBoard(e.currentTarget.checked)
            }}
          />
          {leagues.isPending && <Loader />}
          {leagues.error && <Alert color="red">{leagues.error.message}</Alert>}
          {leagues.data && (
            <>
              <Group>
                <LeaguePicker
                  leagues={leagues.data}
                  value={league}
                  onChange={(v) => {
                    setLeague(v)
                    setClubId(null)
                  }}
                />
              </Group>
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
              onClick={() =>
                clubId !== null &&
                void newCareer
                  .mutateAsync({
                    slot: Number(slot),
                    clubId,
                    manager: manager || 'Manager',
                    budget: budgetMillions === '' ? null : Math.min(MAX_BUDGET_EUR, toEuros(Number(budgetMillions) * 1_000_000)),
                    boardEnabled: board,
                  })
                  .then(goHome, ignore)
              }
            >
              Start career
            </Button>
          </Group>
        </Stack>
      </Stack>
    </Container>
  )
}
