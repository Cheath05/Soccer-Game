import { Alert, Badge, Button, Card, Collapse, Container, Group, Loader, NumberInput, SegmentedControl, SimpleGrid, Stack, Switch, Text, TextInput, Title, UnstyledButton } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import { useLoadCareer, useNewCareer, useSaves, useWorldLeagues } from '../api/hooks'
import LeaguePicker from '../components/LeaguePicker'
import { Crest } from '../components/PhoneNav'
import VersionTag from '../components/VersionTag'
import { AccountFooter } from '../components/AuthGate'
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
  // The slot to start in: the first free one, until the player picks.
  const [slotChoice, setSlot] = useState<string | null>(null)
  const [options, setOptions] = useState(false)

  const selectedLeague = leagues.data?.find((l) => l.key === league)
  const firstFree = saves.data?.find((s) => !s.has_save && !s.has_autosave)?.slot
  const slot = slotChoice ?? String(firstFree ?? 1)
  const slotInfo = saves.data?.find((s) => String(s.slot) === slot)
  // Go home once a career is started or loaded. Awaited on the mutation itself, not via
  // mutate's onSuccess: the refetch that follows can unmount this page (the layout shows a
  // loader while the career query reloads), and TanStack Query then drops that callback,
  // leaving /start on screen. Errors are shown from the mutation's own state.
  const goHome = () => void navigate({ to: '/' })
  const ignore = () => undefined

  const taken = (saves.data ?? []).filter((s) => s.has_save || s.has_autosave)
  const free = (saves.data ?? []).filter((s) => !s.has_save && !s.has_autosave).map((s) => s.slot)
  const start = () =>
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

  return (
    <Container size="md" px="sm" pb="xl" pt={0}>
      <Stack gap="lg">
        <div className="fs-start-hero">
          <svg className="fs-start-pitch" viewBox="0 0 400 220" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
            <g fill="none" stroke="currentColor" strokeWidth="1.5">
              <rect x="20" y="-40" width="360" height="300" rx="4" />
              <line x1="20" y1="110" x2="380" y2="110" />
              <circle cx="200" cy="110" r="46" />
              <rect x="120" y="-40" width="160" height="62" />
              <rect x="120" y="198" width="160" height="62" />
            </g>
            <circle cx="200" cy="110" r="3" fill="currentColor" />
          </svg>
          <div className="fs-start-hero-text">
            <Title order={1} fz={64} lh={0.9}>
              Foot<span className="fs-accent">sim</span>
            </Title>
            <Text c="dark.1" mt={8} fz="lg">
              Your club. Your tactics. Every match played out.
            </Text>
            {hasCareer && (
              <Button mt="md" size="md" onClick={goHome}>
                Back to career
              </Button>
            )}
          </div>
        </div>
        {error && <Alert color="red">{error.message}</Alert>}

        {taken.length > 0 && (
          <Stack gap="sm">
            <Title order={3}>Continue</Title>
            <SimpleGrid cols={{ base: 1, sm: taken.length > 1 ? 2 : 1 }} spacing="sm">
              {taken.map((s) => (
                <Card key={s.slot} withBorder className="fs-hero" padding="md">
                  <Group wrap="nowrap" gap="sm" align="center">
                    <Crest name={s.club ?? 'Career'} size={52} mine />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <Text className="fs-num" fz={26} lh={1.05} tt="uppercase" truncate>
                        {s.club ?? 'Career'}
                      </Text>
                      <Text size="sm" c="dimmed" truncate>
                        {s.manager ?? ''} {s.game_date ? `· ${longDate(s.game_date)}` : ''}
                      </Text>
                    </div>
                    <Stack gap={4} align="flex-end" style={{ flexShrink: 0 }}>
                      <span className="fs-label">Slot {s.slot}</span>
                      {s.active && <Badge color="teal">Playing</Badge>}
                    </Stack>
                  </Group>
                  <Group gap="xs" grow mt="md">
                    {s.has_save && (
                      <Button size="md" loading={loadCareer.isPending} onClick={() => void loadCareer.mutateAsync({ slot: s.slot }).then(goHome, ignore)}>
                        Load
                      </Button>
                    )}
                    {s.has_autosave && (
                      <Button size="md" variant="default" onClick={() => void loadCareer.mutateAsync({ slot: s.slot, autosave: true }).then(goHome, ignore)}>
                        Autosave
                      </Button>
                    )}
                  </Group>
                </Card>
              ))}
            </SimpleGrid>
            {loadCareer.error && <Alert color="red">{loadCareer.error.message}</Alert>}
          </Stack>
        )}

        <Stack gap="sm">
          <Group justify="space-between" align="baseline">
            <Title order={3}>New career</Title>
            {free.length > 0 && taken.length > 0 && (
              <Text size="xs" c="dimmed">
                {free.length === 1 ? `Slot ${free[0]} is free` : `Slots ${free.join(' and ')} are free`}
              </Text>
            )}
          </Group>

          <Card withBorder padding="md">
            <Step n={1} title="You" />
            <Stack gap="sm" mt="sm">
              <TextInput size="md" label="Manager name" placeholder="Your name" value={manager} onChange={(e) => setManager(e.currentTarget.value)} />
              <div>
                <Text size="sm" fw={500} mb={4}>
                  Save slot
                </Text>
                <SegmentedControl
                  fullWidth
                  value={slot}
                  onChange={setSlot}
                  data={['1', '2', '3'].map((n) => ({ value: n, label: `Slot ${n}${free.includes(Number(n)) || !saves.data ? '' : ' · used'}` }))}
                />
              </div>
              {slotInfo?.has_save && <Alert color="yellow" variant="light">Slot {slot} already has a career. Starting a new one replaces it.</Alert>}
            </Stack>
          </Card>

          <Card withBorder padding="md">
            <Step n={2} title="Your club" />
            <Stack gap="sm" mt="sm">
              {leagues.isPending && <Loader />}
              {leagues.error && <Alert color="red">{leagues.error.message}</Alert>}
              {leagues.data && (
                <>
                  <LeaguePicker
                    leagues={leagues.data}
                    value={league}
                    onChange={(v) => {
                      setLeague(v)
                      setClubId(null)
                    }}
                  />
                  <SimpleGrid cols={{ base: 2, sm: 3 }} spacing="xs">
                    {selectedLeague?.clubs.map((c) => (
                      <UnstyledButton key={c.id} onClick={() => setClubId(c.id)} className="fs-club" data-picked={clubId === c.id || undefined}>
                        <Crest name={c.name} size={34} mine={clubId === c.id} />
                        <div style={{ minWidth: 0 }}>
                          <Text fw={600} size="sm" truncate>
                            {c.name}
                          </Text>
                          <Text size="xs" c="dimmed" truncate>
                            {c.average_overall.toFixed(1)} ovr · rep {c.reputation}
                          </Text>
                        </div>
                      </UnstyledButton>
                    ))}
                  </SimpleGrid>
                </>
              )}
            </Stack>
          </Card>

          <Card withBorder padding="md">
            <UnstyledButton w="100%" onClick={() => setOptions((o) => !o)} aria-expanded={options}>
              <Group justify="space-between" wrap="nowrap">
                <Step n={3} title="Options" />
                <Text size="sm" c="dimmed">
                  {board ? 'Board on' : 'No board'} · {CURRENCIES[currency].label}
                  {budgetMillions === '' ? '' : ' · sandbox'} {options ? '▴' : '▾'}
                </Text>
              </Group>
            </UnstyledButton>
            <Collapse expanded={options}>
              <Stack gap="md" mt="md">
                <Switch
                  label="Board expectations"
                  description="Off means no targets and no sacking, and your budget is all your cash."
                  checked={board}
                  onChange={(e) => {
                    setBoardTouched(true)
                    setBoard(e.currentTarget.checked)
                  }}
                />
                <div>
                  <Text size="sm" fw={500} mb={4}>
                    Currency
                  </Text>
                  <SegmentedControl
                    value={currency}
                    onChange={(v) => setCurrency(v as Currency)}
                    data={(Object.keys(CURRENCIES) as Currency[]).map((c) => ({ value: c, label: CURRENCIES[c].label }))}
                  />
                </div>
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
                />
              </Stack>
            </Collapse>
          </Card>

          {newCareer.error && <Alert color="red">{newCareer.error.message}</Alert>}
          <Group style={clubId !== null ? { position: 'sticky', bottom: 'calc(12px + env(safe-area-inset-bottom))', zIndex: 5 } : undefined}>
            <Button size="lg" fullWidth disabled={clubId === null} loading={newCareer.isPending} onClick={start}>
              {clubId === null ? 'Pick a club to start' : `Start with ${selectedLeague?.clubs.find((c) => c.id === clubId)?.name ?? 'this club'}`}
            </Button>
          </Group>
        </Stack>

        <Stack gap={4} align="center" mt="md">
          <VersionTag />
          <AccountFooter />
        </Stack>
      </Stack>
    </Container>
  )
}

function Step({ n, title }: { n: number; title: string }) {
  return (
    <Group gap="sm" wrap="nowrap">
      <span className="fs-step">{n}</span>
      <Text className="fs-num" fz={22} lh={1} tt="uppercase">
        {title}
      </Text>
    </Group>
  )
}
