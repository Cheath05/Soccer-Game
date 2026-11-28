import { Alert, Badge, Button, Card, Collapse, Container, Group, Loader, Modal, NumberInput, Paper, Progress, SegmentedControl, Select, SimpleGrid, Stack, Switch, Text, TextInput, Title, UnstyledButton } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import { useCollegePrograms, useDeleteCareer, useLoadCareer, useNewCareer, useSaves, useStartProgress, useWorldLeagues, useWorldNations } from '../api/hooks'
import LeaguePicker from '../components/LeaguePicker'
import { tierStars } from '../lib/college'
import SimulationPicker from '../components/SimulationPicker'
import { Crest } from '../components/PhoneNav'
import VersionTag from '../components/VersionTag'
import { AccountFooter } from '../components/AuthGate'
import type { SaveSlot, StartProgress } from '../api/types'
import { CURRENCIES, type Currency, longDate, setCurrency, toEuros, useCurrency } from '../lib/format'

const MAX_BUDGET_EUR = 10_000_000_000 // the most the sandbox gives (the server's limit)

export default function StartPage({ hasCareer, error }: { hasCareer: boolean; error: Error | null }) {
  const saves = useSaves()
  const leagues = useWorldLeagues()
  const newCareer = useNewCareer()
  // Setting up a new career takes several seconds: the page shows which stage it's on.
  const startProgress = useStartProgress(newCareer.isPending)
  const loadCareer = useLoadCareer()
  const deleteCareer = useDeleteCareer()
  // The save waiting for the player to confirm its deletion.
  const [deleting, setDeleting] = useState<SaveSlot | null>(null)
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
                  <Group gap="xs" mt="md" wrap="nowrap">
                    {s.has_save && (
                      <Button size="md" style={{ flex: 1 }} loading={loadCareer.isPending} onClick={() => void loadCareer.mutateAsync({ slot: s.slot }).then(goHome, ignore)}>
                        Load
                      </Button>
                    )}
                    {s.has_autosave && (
                      <Button size="md" style={{ flex: 1 }} variant="default" onClick={() => void loadCareer.mutateAsync({ slot: s.slot, autosave: true }).then(goHome, ignore)}>
                        Autosave
                      </Button>
                    )}
                    <Button size="md" variant="subtle" color="red" onClick={() => setDeleting(s)} aria-label={`Delete the save in slot ${s.slot}`}>
                      Delete
                    </Button>
                  </Group>
                </Card>
              ))}
            </SimpleGrid>
            {loadCareer.error && <Alert color="red">{loadCareer.error.message}</Alert>}
            {deleteCareer.error && <Alert color="red">{deleteCareer.error.message}</Alert>}
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
              {(slotInfo?.has_save || slotInfo?.has_autosave) && (
                <Alert color="yellow" variant="light">
                  Slot {slot} has your {slotInfo.club ?? 'career'} career{slotInfo.manager ? ` (${slotInfo.manager})` : ''}. Starting a new one replaces it.
                </Alert>
              )}
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
                  { value: 'club', label: 'Pro club' },
                  { value: 'college', label: 'NCAA college' },
                  { value: 'nation', label: 'Country' },
                ]}
              />
              {country && (
                <>
                  <Text size="sm" c="dimmed">
                    Manage a national team without a club: pick its squad for every international window and tournament, set its tactics and play its matches. Continue moves on from one window to the next. You can move to another country later, from International → My country.
                  </Text>
                  {nations.error && <Alert color="red">{nations.error.message}</Alert>}
                  <PickSelect
                    label="Country"
                    placeholder="Find a country"
                    value={nationCode}
                    onChange={setNationCode}
                    options={(nations.data ?? []).map((n) => ({ value: n.code, label: n.name, detail: `#${n.rank} in the world · ${n.confederation}` }))}
                  />
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
                  <PickSelect
                    label="Program"
                    placeholder={`Find a program in the ${colleges.data?.find((c) => c.key === conference)?.short_name ?? 'conference'}`}
                    value={program}
                    onChange={setProgram}
                    options={programs.map((p) => ({ value: p.name, label: p.school, detail: `${tierStars(p.tier)} tier ${p.tier} of 5 · ${p.state}` }))}
                  />
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
                  <PickSelect
                    label="Club"
                    placeholder={`Find a club in ${selectedLeague?.name ?? 'this league'}`}
                    value={clubId === null ? null : String(clubId)}
                    onChange={(v) => setClubId(v === null ? null : Number(v))}
                    options={[...(selectedLeague?.clubs ?? [])]
                      .sort((a, b) => b.average_overall - a.average_overall)
                      .map((c) => ({ value: String(c.id), label: c.name, detail: `${c.average_overall.toFixed(1)} overall · reputation ${c.reputation}` }))}
                  />
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
          <Stack gap="xs" style={picked !== null ? { position: 'sticky', bottom: 'calc(12px + env(safe-area-inset-bottom))', zIndex: 5 } : undefined}>
            {/* Above the button, so it stays in view with it. */}
            {newCareer.isPending && <StartingCareer progress={startProgress.data ?? null} />}
            <Button size="lg" fullWidth disabled={picked === null} loading={newCareer.isPending} onClick={start}>
              {picked === null ? (college ? 'Pick a program to start' : country ? 'Pick a country to start' : 'Pick a club to start') : `Start with ${picked}`}
            </Button>
          </Stack>
        </Stack>

        <Modal opened={deleting !== null} onClose={() => setDeleting(null)} title="Delete this save?" centered>
          {deleting && (
            <Stack gap="md">
              <Text size="sm">
                Slot {deleting.slot}: <b>{deleting.club ?? 'Career'}</b>
                {deleting.manager ? ` (${deleting.manager}` : ''}
                {deleting.game_date ? `${deleting.manager ? ', ' : ' ('}${longDate(deleting.game_date)}` : ''}
                {deleting.manager || deleting.game_date ? ')' : ''}. Its save, autosave and backups are deleted for good: this can’t be undone.
                {deleting.active ? ' It’s the career you’re playing, so it closes too.' : ''}
              </Text>
              <Group justify="flex-end" gap="xs">
                <Button variant="default" onClick={() => setDeleting(null)}>
                  Keep it
                </Button>
                <Button color="red" loading={deleteCareer.isPending} onClick={() => void deleteCareer.mutateAsync(deleting.slot).then(() => setDeleting(null), ignore)}>
                  Delete
                </Button>
              </Group>
            </Stack>
          )}
        </Modal>

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

type PickOption = { value: string; label: string; detail: string }

/** A searchable dropdown of clubs, programs or countries, each with its crest and a line of detail,
 * and the one picked shown below it. */
function PickSelect({ label, placeholder, value, onChange, options }: { label: string; placeholder: string; value: string | null; onChange: (v: string | null) => void; options: PickOption[] }) {
  const byValue = new Map(options.map((o) => [o.value, o]))
  const picked = value === null ? undefined : byValue.get(value)
  return (
    <Stack gap="xs">
      <Select
        size="md"
        label={label}
        placeholder={placeholder}
        searchable
        clearable
        nothingFoundMessage="Nothing matches"
        maxDropdownHeight={360}
        value={value}
        onChange={onChange}
        data={options.map((o) => ({ value: o.value, label: o.label }))}
        renderOption={({ option }) => (
          <Group gap="sm" wrap="nowrap">
            <Crest name={option.label} size={30} />
            <div style={{ minWidth: 0 }}>
              <Text size="sm" fw={600} truncate>
                {option.label}
              </Text>
              <Text size="xs" c="dimmed" truncate>
                {byValue.get(option.value)?.detail}
              </Text>
            </div>
          </Group>
        )}
      />
      {picked && (
        <div className="fs-club" data-picked>
          <Crest name={picked.label} size={44} mine />
          <div style={{ minWidth: 0 }}>
            <Text fw={700} truncate>
              {picked.label}
            </Text>
            <Text size="sm" c="dimmed" truncate>
              {picked.detail}
            </Text>
          </div>
        </div>
      )}
    </Stack>
  )
}

/** The new career being set up: which stage it's on, and a bar for how far it has got. */
function StartingCareer({ progress }: { progress: StartProgress | null }) {
  const value = progress ? (100 * progress.done) / progress.total : 0
  return (
    <Paper withBorder radius="md" p="sm">
      <Stack gap={6}>
        <Progress value={value} animated aria-label="Career setup progress" />
        <Text size="sm" c="dimmed" ta="center">
          {progress ? `${progress.step}… (${progress.done + 1} of ${progress.total})` : 'Setting up your career…'}
        </Text>
      </Stack>
    </Paper>
  )
}
