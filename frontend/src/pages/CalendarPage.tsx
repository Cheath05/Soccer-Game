import { ActionIcon, Badge, Box, Button, Card, Group, Modal, Stack, Text, Title, Tooltip, UnstyledButton } from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import { useCalendar, useCareer, useStartSim } from '../api/hooks'
import type { Fixture } from '../api/types'
import { addDays, longDate, score, shortDate } from '../lib/format'

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const RESULT_COLOR = { W: 'green', D: 'gray', L: 'red' } as const
const PALETTE = ['blue', 'grape', 'teal', 'orange', 'pink', 'cyan', 'indigo', 'lime', 'violet', 'red']

function hash(text: string): number {
  let h = 0
  for (const ch of text) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return h
}

/** A competition keeps one colour wherever it shows. */
const competitionColor = (key: string) => PALETTE[hash(key) % PALETTE.length]

/** A crest-style badge: the club's initials on a colour of its own. */
function Crest({ name, id, size = 20 }: { name: string; id: number; size?: number }) {
  const words = name.replace(/[^A-Za-z0-9 ]/g, '').split(' ').filter(Boolean)
  const letters = (words.length > 1 ? words.slice(0, 2).map((w) => w[0]).join('') : (words[0] ?? '?').slice(0, 2)).toUpperCase()
  return (
    <Box
      aria-hidden
      style={{
        flexShrink: 0,
        width: size,
        height: size,
        borderRadius: '50%',
        display: 'grid',
        placeItems: 'center',
        fontSize: size * 0.42,
        fontWeight: 700,
        color: 'white',
        background: `var(--mantine-color-${PALETTE[(id * 7) % PALETTE.length]}-filled)`,
      }}
    >
      {letters}
    </Box>
  )
}

function monthStart(iso: string): string {
  return `${iso.slice(0, 7)}-01`
}

function shiftMonth(first: string, by: number): string {
  const d = new Date(`${first}T12:00:00Z`)
  d.setUTCMonth(d.getUTCMonth() + by)
  return d.toISOString().slice(0, 10)
}

// Index of the weekday, Monday first (0..6).
function weekday(iso: string): number {
  return (new Date(`${iso}T12:00:00Z`).getUTCDay() + 6) % 7
}

function monthLabel(first: string): string {
  return new Date(`${first}T12:00:00Z`).toLocaleDateString('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' })
}

function outcome(f: Fixture, clubId: number): 'W' | 'D' | 'L' | null {
  if (f.status !== 'played' || f.home_goals === null || f.away_goals === null) return null
  const home = f.home.id === clubId
  let mine = home ? f.home_goals : f.away_goals
  let theirs = home ? f.away_goals : f.home_goals
  if (mine === theirs && f.home_pens !== null && f.away_pens !== null) {
    mine = home ? f.home_pens : f.away_pens
    theirs = home ? f.away_pens : f.home_pens
  }
  return mine > theirs ? 'W' : mine < theirs ? 'L' : 'D'
}

export default function CalendarPage() {
  const career = useCareer().data
  const start = useStartSim()
  const navigate = useNavigate()
  const narrow = useMediaQuery('(max-width: 640px)') ?? false
  const [month, setMonth] = useState<string | null>(null)
  const [target, setTarget] = useState<string | null>(null)
  const first = month ?? monthStart(career?.date ?? new Date().toISOString().slice(0, 10))
  const gridStart = addDays(first, -weekday(first))
  const gridEnd = addDays(gridStart, 41)
  const cal = useCalendar(gridStart, gridEnd)
  const soon = useCalendar(career?.date ?? gridStart, addDays(career?.date ?? gridStart, 70))
  if (!career) return null

  const days = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i))
  const data = cal.data
  const windowDays = new Set(data?.window_days ?? [])
  const byDay = new Map<string, Fixture[]>()
  for (const f of data?.fixtures ?? []) byDay.set(f.date, [...(byDay.get(f.date) ?? []), f])
  const inBreak = (d: string) => (data?.international_breaks ?? []).some((b) => b.start <= d && d <= b.end)
  const competitions = new Map<string, string>()
  for (const f of data?.fixtures ?? []) competitions.set(f.competition, f.competition_name)
  const upcoming = (soon.data?.fixtures ?? []).filter((f) => f.status !== 'played' && f.date >= career.date).slice(0, 8)

  const confirm = () => {
    if (target) start.mutate(target)
    setTarget(null)
  }

  const chip = (f: Fixture) => {
    const home = f.home.id === career.club.id
    const opp = home ? f.away : f.home
    const res = outcome(f, career.club.id)
    const played = f.status === 'played'
    const color = competitionColor(f.competition)
    const where = home ? 'H' : f.neutral ? 'N' : 'A'
    return (
      <Tooltip key={f.id} label={`${f.competition_name}: ${f.home.name} ${played ? score(f) : 'v'} ${f.away.name}`} withinPortal>
        <UnstyledButton
          data-testid="calendar-fixture"
          onClick={(e) => {
            if (!played) return
            e.stopPropagation()
            void navigate({ to: '/match/$fixtureId', params: { fixtureId: String(f.id) } })
          }}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: narrow ? 0 : 4,
            justifyContent: narrow ? 'center' : undefined,
            width: '100%',
            marginTop: 3,
            padding: narrow ? '1px 0' : '2px 4px',
            borderRadius: 6,
            fontSize: 11,
            lineHeight: 1.2,
            background: `var(--mantine-color-${color}-light)`,
            borderLeft: narrow ? undefined : `3px solid var(--mantine-color-${color}-filled)`,
            cursor: played ? 'pointer' : undefined,
          }}
        >
          {narrow ? (
            <Crest name={opp.name} id={opp.id} size={18} />
          ) : (
            <>
              <Crest name={opp.name} id={opp.id} size={16} />
              <Text fz={11} fw={600} truncate style={{ flex: 1, minWidth: 0 }}>
                {where} {opp.name}
              </Text>
              {res ? (
                <Badge size="xs" radius="sm" color={RESULT_COLOR[res]} variant="filled" px={4}>
                  {res} {f.home_goals}–{f.away_goals}
                </Badge>
              ) : (
                <Text fz={10} c="dimmed">
                  {where}
                </Text>
              )}
            </>
          )}
        </UnstyledButton>
      </Tooltip>
    )
  }

  return (
    <Stack gap="md">
      <Group justify="space-between" wrap="wrap">
        <Title order={2}>Calendar</Title>
        <Group gap="xs">
          <ActionIcon variant="default" size="lg" radius="xl" aria-label="Previous month" onClick={() => setMonth(shiftMonth(first, -1))}>
            ‹
          </ActionIcon>
          <Text fw={700} fz="lg" miw={150} ta="center">
            {monthLabel(first)}
          </Text>
          <ActionIcon variant="default" size="lg" radius="xl" aria-label="Next month" onClick={() => setMonth(shiftMonth(first, 1))}>
            ›
          </ActionIcon>
          <Button variant="light" size="xs" radius="xl" onClick={() => setMonth(null)}>
            Today
          </Button>
        </Group>
      </Group>

      <Group align="start" gap="lg" wrap="wrap">
        <Stack gap="xs" style={{ flex: '1 1 480px', minWidth: 0 }}>
          <Card withBorder radius="md" p={narrow ? 6 : 'sm'}>
            <Box style={{ display: 'grid', gridTemplateColumns: 'repeat(7, minmax(0, 1fr))', gap: narrow ? 3 : 6 }}>
              {WEEKDAYS.map((w) => (
                <Text key={w} ta="center" fz={11} fw={600} c="dimmed" tt="uppercase" lts={0.5}>
                  {narrow ? w[0] : w}
                </Text>
              ))}
              {days.map((d) => {
                const fixtures = byDay.get(d) ?? []
                const isToday = d === career.date
                const future = d > career.date
                const otherMonth = d.slice(0, 7) !== first.slice(0, 7)
                const window = windowDays.has(d)
                const seasonEdge = d === data?.season_start ? 'Season starts' : d === data?.season_end ? 'Season ends' : null
                return (
                  <Box
                    key={d}
                    data-date={d}
                    data-testid="calendar-day"
                    onClick={future ? () => setTarget(d) : undefined}
                    role={future ? 'button' : undefined}
                    aria-label={future ? `Sim to ${longDate(d)}` : undefined}
                    tabIndex={future ? 0 : undefined}
                    onKeyDown={future ? (e) => (e.key === 'Enter' || e.key === ' ') && setTarget(d) : undefined}
                    style={{
                      minHeight: narrow ? 52 : 84,
                      minWidth: 0,
                      padding: narrow ? 2 : 5,
                      overflow: 'hidden',
                      cursor: future ? 'pointer' : 'default',
                      opacity: otherMonth ? 0.45 : 1,
                      background: inBreak(d) ? 'var(--mantine-color-blue-light)' : 'var(--mantine-color-body)',
                      border: isToday ? '2px solid var(--mantine-color-blue-filled)' : '1px solid var(--mantine-color-default-border)',
                      borderTop: window && !isToday ? '3px solid var(--mantine-color-yellow-5)' : undefined,
                      borderRadius: 8,
                      transition: 'box-shadow 120ms, transform 120ms',
                    }}
                    onMouseEnter={(e) => future && (e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.18)')}
                    onMouseLeave={(e) => (e.currentTarget.style.boxShadow = 'none')}
                  >
                    <Group gap={2} justify="space-between" wrap="nowrap">
                      {isToday ? (
                        <Box style={{ background: 'var(--mantine-color-blue-filled)', color: 'white', borderRadius: 999, minWidth: 20, height: 20, display: 'grid', placeItems: 'center', fontSize: 11, fontWeight: 700 }}>
                          {Number(d.slice(8))}
                        </Box>
                      ) : (
                        <Text fz="xs" fw={500} c={future ? undefined : 'dimmed'}>
                          {Number(d.slice(8))}
                        </Text>
                      )}
                      {seasonEdge && !narrow && (
                        <Text fz={9} c="dimmed" truncate>
                          {seasonEdge}
                        </Text>
                      )}
                    </Group>
                    {fixtures.map(chip)}
                  </Box>
                )
              })}
            </Box>
          </Card>

          <Group gap="md" fz="xs" c="dimmed" wrap="wrap">
            {[...competitions].map(([key, name]) => (
              <Group key={key} gap={5}>
                <Box w={10} h={10} style={{ borderRadius: 3, background: `var(--mantine-color-${competitionColor(key)}-filled)` }} />
                {name}
              </Group>
            ))}
            <Group gap={5}>
              <Box w={14} h={0} style={{ borderTop: '3px solid var(--mantine-color-yellow-5)' }} />
              Transfer window
            </Group>
            <Group gap={5}>
              <Box w={12} h={12} style={{ borderRadius: 3, background: 'var(--mantine-color-blue-light)' }} />
              International break
            </Group>
            <Group gap={4}>
              <Badge size="xs" color="green" px={4}>W</Badge>
              <Badge size="xs" color="gray" px={4}>D</Badge>
              <Badge size="xs" color="red" px={4}>L</Badge>
            </Group>
            <Text span fz="xs">
              Click a coming day to sim to it.
            </Text>
          </Group>
        </Stack>

        <Card withBorder radius="md" style={{ flex: '1 1 260px', maxWidth: narrow ? undefined : 340 }}>
          <Text fw={700} mb="xs">
            Up next
          </Text>
          <Stack gap={6}>
            {upcoming.length === 0 && (
              <Text size="sm" c="dimmed">
                No more matches scheduled in the next ten weeks.
              </Text>
            )}
            {upcoming.map((f) => {
              const home = f.home.id === career.club.id
              const opp = home ? f.away : f.home
              const color = competitionColor(f.competition)
              return (
                <UnstyledButton
                  key={f.id}
                  onClick={() => setTarget(f.date)}
                  disabled={f.date <= career.date}
                  style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 8px', borderRadius: 8, borderLeft: `4px solid var(--mantine-color-${color}-filled)`, background: 'var(--mantine-color-default-hover)' }}
                >
                  <Crest name={opp.name} id={opp.id} size={26} />
                  <Box style={{ flex: 1, minWidth: 0 }}>
                    <Text size="sm" fw={600} truncate>
                      {home ? 'v' : f.neutral ? 'v' : '@'} {opp.name}
                    </Text>
                    <Text size="xs" c="dimmed" truncate>
                      {f.competition_name}
                    </Text>
                  </Box>
                  <Text size="xs" fw={600} ta="right">
                    {f.date === career.date ? 'Today' : shortDate(f.date)}
                  </Text>
                </UnstyledButton>
              )
            })}
          </Stack>
        </Card>
      </Group>

      {start.error && (
        <Text c="red" size="sm">
          {start.error.message}
        </Text>
      )}

      <Modal opened={target !== null} onClose={() => setTarget(null)} title={target ? `Sim to ${longDate(target)}?` : ''} centered>
        <Stack>
          <Text size="sm">Your matches on the way are played instantly; that day&apos;s matches are left for you.</Text>
          <Text size="sm" c="dimmed">
            It stops early if a club bids for one of your players, or at the end of the season.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setTarget(null)}>
              Cancel
            </Button>
            <Button onClick={confirm}>Sim</Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}
