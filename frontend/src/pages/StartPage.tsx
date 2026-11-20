import { Alert, Badge, Button, Card, Collapse, Container, Group, Loader, NumberInput, SegmentedControl, Select, SimpleGrid, Stack, Switch, Text, TextInput, Title, UnstyledButton } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import { useCollegePrograms, useLoadCareer, useNewCareer, useSaves, useWorldLeagues, useWorldNations } from '../api/hooks'
import LeaguePicker from '../components/LeaguePicker'
import { tierStars } from '../lib/college'
import SimulationPicker from '../components/SimulationPicker'
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
  // A professional club, an NCAA program to coach (W9c), or only a country (no club).
  const [kind, setKind] = useState<'club' | 'college' | 'nation'>('club')
  const nations = useWorldNations()
  const [nationCode, setNationCode] = useState<string | null>(null)
  const country = kind === 'nation'
  const colleges = useCollegePrograms()
  const [conference, setConference] = useState('ACC')
  const [program, setProgram] = useState<string | null>(null)
  const [collegeMode, setCollegeMode] = useState<'classic' | 'builder'>('classic')
  const college = kind === 'college'
  // The slot to start in: the first free one, until the player picks.
  const [slotChoice, setSlot] = useState<string | null>(null)
  const [options, setOptions] = useState(false)
  // The leagues given fast results instead of full simulation (none: everything fully simulated).
  const [fast, setFast] = useState<string[]>([])

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
  const picked = country ? (nations.data?.find((n) => n.code === nationCode)?.name ?? null) : college ? program : clubId !== null ? (selectedLeague?.clubs.find((c) => c.id === clubId)?.name ?? 'this club') : null
  const userLeague = college ? 'NCAA' : country ? null : league
  // No board, budget or transfers: a college program's, or a country's.
  const noClub = college || country
  const programs = colleges.data?.find((c) => c.key === conference)?.programs ?? []
  const start = () =>
    picked !== null &&
    void newCareer
      .mutateAsync({
        slot: Number(slot),
        clubId: noClub ? null : clubId,
        collegeProgram: college ? program : null,
        collegeMode,
        nationCode: country ? nationCode : null,
        manager: manager || (college ? 'Coach' : 'Manager'),
        budget: noClub || budgetMillions === '' ? null : Math.min(MAX_BUDGET_EUR, toEuros(Number(budgetMillions) * 1_000_000)),
        boardEnabled: board && !noClub,
        fastLeagues: fast.filter((k) => k !== userLeague),
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
            <Step n={2} title={college ? 'Your program' : country ? 'Your country' : 'Your club'} />
            <Stack gap="sm" mt="sm">
              <SegmentedControl
                fullWidth
                value={kind}
                onChange={(v) => setKind(v as 'club' | 'college' | 'nation')}
                data={[
                  { value: 'club', label: 'Professional club' },
                  { value: 'college', label: 'NCAA program' },
                  { value: 'nation', label: 'Manage a country' },
                ]}
              />
              {country && (
                <>
                  <Text size="sm" c="dimmed">
                    Manage a national team without a club: pick its squad for every international window and tournament, set its tactics and play its matches. Continue moves on from one window to the next. You can move to another country later, from International → My country.
                  </Text>
                  {nations.error && <Alert color="red">{nations.error.message}</Alert>}
                  <Select
                    label="Country"
                    searchable
                    placeholder="Find a country"
                    value={nationCode}
                    onChange={setNationCode}
                    data={(nations.data ?? []).map((n) => ({ value: n.code, label: `${n.name} (#${n.rank})` }))}
                  />
                  <SimpleGrid cols={{ base: 2, sm: 3 }} spacing="xs">
                    {(nations.data ?? []).slice(0, 12).map((n) => (
                      <UnstyledButton key={n.code} onClick={() => setNationCode(n.code)} className="fs-club" data-picked={nationCode === n.code || undefined}>
                        <Crest name={n.name} size={34} mine={nationCode === n.code} />
                        <div style={{ minWidth: 0 }}>
                          <Text fw={600} size="sm" truncate>
                            {n.name}
                          </Text>
                          <Text size="xs" c="dimmed" truncate>
                            #{n.rank} · {n.confederation}
                          </Text>
                        </div>
                      </UnstyledButton>
                    ))}
                  </SimpleGrid>
                </>
              )}
              {college && (
                <>
                  <Text size="sm" c="dimmed">
                    Coach a US college soccer program: recruit high-school players with scholarship offers, play the conference season and chase the College Cup. Your best players go on to the MLS SuperDraft.
                  </Text>
                  {colleges.error && <Alert color="red">{colleges.error.message}</Alert>}
                  {colleges.data && (
                    <Select
                      label="Conference"
                      searchable
                      allowDeselect={false}
                      value={conference}
                      onChange={(v) => {
                        if (v) setConference(v)
                        setProgram(null)
                      }}
                      data={colleges.data.map((c) => ({ value: c.key, label: `${c.short_name} (${c.programs.length})` }))}
                    />
                  )}
                  <div>
                    <Text size="sm" fw={500} mb={4}>
                      Game mode
                    </Text>
                    <SegmentedControl
                      fullWidth
                      value={collegeMode}
                      onChange={(v) => setCollegeMode(v as 'classic' | 'builder')}
                      data={[
                        { value: 'classic', label: 'Classic' },
                        { value: 'builder', label: 'Program builder' },
                      ]}
                    />
                    <Text size="xs" c="dimmed" mt={4}>
                      {collegeMode === 'builder'
                        ? 'Money every season (the athletic department, ticket sales, boosters, NCAA payouts) to spend on scholarships, training facilities that speed your players’ growth, and a stadium whose crowd unsettles visiting teams. The other programs build too.'
                        : 'Recruit, coach and win: scholarship money is set by your program’s tier.'}
                    </Text>
                  </div>
                  <SimpleGrid cols={{ base: 2, sm: 3 }} spacing="xs">
                    {programs.map((p) => (
                      <UnstyledButton key={p.name} onClick={() => setProgram(p.name)} className="fs-club" data-picked={program === p.name || undefined}>
                        <Crest name={p.name} size={34} mine={program === p.name} />
                        <div style={{ minWidth: 0 }}>
                          <Text fw={600} size="sm" truncate>
                            {p.school}
                          </Text>
                          <Text size="xs" c="dimmed" truncate title={`Program tier ${p.tier} of 5`}>
                            {tierStars(p.tier)} · {p.state}
                          </Text>
                        </div>
                      </UnstyledButton>
                    ))}
                  </SimpleGrid>
                </>
              )}
              {!noClub && leagues.isPending && <Loader />}
              {!noClub && leagues.error && <Alert color="red">{leagues.error.message}</Alert>}
              {!noClub && leagues.data && (
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
                  {college ? 'College' : country ? 'Country' : board ? 'Board on' : 'No board'} · {CURRENCIES[currency].label}
                  {!noClub && budgetMillions !== '' ? ' · sandbox' : ''}
                  {fast.filter((k) => k !== userLeague).length > 0 ? ' · fast leagues' : ''} {options ? '▴' : '▾'}
                </Text>
              </Group>
            </UnstyledButton>
            <Collapse expanded={options}>
              <Stack gap="md" mt="md">
                {noClub ? (
                  <Text size="sm" c="dimmed">
                    {college
                      ? 'A college program has no board, budget or transfers: your players come from recruiting.'
                      : 'A country has no board, budget or transfers: you call up its players.'}
                  </Text>
                ) : (
                  <Switch
                    label="Board expectations"
                    description="Off means no targets and no sacking, and your budget is all your cash."
                    checked={board}
                    onChange={(e) => {
                      setBoardTouched(true)
                      setBoard(e.currentTarget.checked)
                    }}
                  />
                )}
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
                {!noClub && <NumberInput
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
                />}
                <div>
                  <Text size="sm" fw={500} mb={4}>
                    Simulation
                  </Text>
                  <SimulationPicker fast={fast} onChange={setFast} userLeague={userLeague} />
                </div>
              </Stack>
            </Collapse>
          </Card>

          {newCareer.error && <Alert color="red">{newCareer.error.message}</Alert>}
          <Group style={picked !== null ? { position: 'sticky', bottom: 'calc(12px + env(safe-area-inset-bottom))', zIndex: 5 } : undefined}>
            <Button size="lg" fullWidth disabled={picked === null} loading={newCareer.isPending} onClick={start}>
              {picked === null ? (college ? 'Pick a program to start' : country ? 'Pick a country to start' : 'Pick a club to start') : `Start with ${picked}`}
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
