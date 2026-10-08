import { Box, Button, Group, Modal, Stack, Text, Title, Tooltip, UnstyledButton } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import { useCalendar, useCareer, useStartSim } from '../api/hooks'
import type { Fixture } from '../api/types'
import { addDays, longDate, score } from '../lib/format'

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const RESULT_COLOR = { W: 'var(--mantine-color-green-light)', D: 'var(--mantine-color-gray-light)', L: 'var(--mantine-color-red-light)' } as const

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
  const [month, setMonth] = useState<string | null>(null)
  const [target, setTarget] = useState<string | null>(null)
  const first = month ?? monthStart(career?.date ?? new Date().toISOString().slice(0, 10))
  const gridStart = addDays(first, -weekday(first))
  const gridEnd = addDays(gridStart, 41)
  const cal = useCalendar(gridStart, gridEnd)
  if (!career) return null

  const days = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i))
  const data = cal.data
  const windowDays = new Set(data?.window_days ?? [])
  const byDay = new Map<string, Fixture[]>()
  for (const f of data?.fixtures ?? []) byDay.set(f.date, [...(byDay.get(f.date) ?? []), f])
  const inBreak = (d: string) => (data?.international_breaks ?? []).some((b) => b.start <= d && d <= b.end)

  const confirm = () => {
    if (target) start.mutate(target)
    setTarget(null)
  }

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Calendar</Title>
        <Group gap="xs">
          <Button variant="default" size="xs" aria-label="Previous month" onClick={() => setMonth(shiftMonth(first, -1))}>
            ‹
          </Button>
          <Text fw={600} miw={130} ta="center">
            {monthLabel(first)}
          </Text>
          <Button variant="default" size="xs" aria-label="Next month" onClick={() => setMonth(shiftMonth(first, 1))}>
            ›
          </Button>
          <Button variant="light" size="xs" onClick={() => setMonth(null)}>
            Today
          </Button>
        </Group>
      </Group>

      <Group gap="md" fz="xs" c="dimmed">
        <Group gap={4}>
          <Box w={12} h={12} style={{ background: 'var(--mantine-color-yellow-light)', border: '1px solid var(--mantine-color-yellow-6)' }} />
          Transfer window open
        </Group>
        <Group gap={4}>
          <Box w={12} h={12} style={{ background: 'var(--mantine-color-blue-light)' }} />
          International break
        </Group>
        <Text span fz="xs">
          Click a coming day to sim to it.
        </Text>
      </Group>

      <Box
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(7, minmax(0, 1fr))',
          gap: 2,
        }}
      >
        {WEEKDAYS.map((w) => (
          <Text key={w} ta="center" fz="xs" fw={600} c="dimmed">
            {w}
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
                minHeight: 74,
                minWidth: 0,
                padding: 3,
                overflow: 'hidden',
                cursor: future ? 'pointer' : 'default',
                opacity: otherMonth ? 0.55 : 1,
                background: inBreak(d)
                  ? 'var(--mantine-color-blue-light)'
                  : window
                    ? 'var(--mantine-color-yellow-light)'
                    : 'var(--mantine-color-default-hover)',
                border: isToday ? '2px solid var(--mantine-color-blue-filled)' : '1px solid var(--mantine-color-default-border)',
                borderRadius: 4,
              }}
            >
              <Group gap={2} justify="space-between" wrap="nowrap">
                <Text fz="xs" fw={isToday ? 700 : 500}>
                  {Number(d.slice(8))}
                </Text>
                {seasonEdge && (
                  <Text fz={9} c="dimmed" truncate>
                    {seasonEdge}
                  </Text>
                )}
              </Group>
              {fixtures.map((f) => {
                const home = f.home.id === career.club.id
                const opp = home ? f.away : f.home
                const res = outcome(f, career.club.id)
                const played = f.status === 'played'
                return (
                  <Tooltip key={f.id} label={`${f.competition_name}: ${f.home.name} ${played ? score(f) : 'v'} ${f.away.name}`} withinPortal>
                    <UnstyledButton
                      onClick={(e) => {
                        if (!played) return
                        e.stopPropagation()
                        void navigate({ to: '/match/$fixtureId', params: { fixtureId: String(f.id) } })
                      }}
                      style={{
                        display: 'block',
                        width: '100%',
                        marginTop: 2,
                        padding: '1px 3px',
                        borderRadius: 3,
                        fontSize: 11,
                        lineHeight: 1.25,
                        background: res ? RESULT_COLOR[res] : 'var(--mantine-color-body)',
                        border: '1px solid var(--mantine-color-default-border)',
                        cursor: played ? 'pointer' : undefined,
                      }}
                    >
                      <Text fz={11} fw={600} truncate>
                        {home ? 'H' : f.neutral ? 'N' : 'A'} {opp.name}
                      </Text>
                      <Text fz={10} c="dimmed" truncate>
                        {played ? score(f) : f.competition_name}
                      </Text>
                    </UnstyledButton>
                  </Tooltip>
                )
              })}
            </Box>
          )
        })}
      </Box>

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
