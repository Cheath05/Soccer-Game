import { Badge, Button, Group, List, Menu, Modal, Progress, ScrollArea, Stack, Text, TextInput } from '@mantine/core'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import { useSimStatus, useStartSim, useStopSim } from '../api/hooks'
import type { Career, SimResult, SimStatus } from '../api/types'
import { addDays, addMonths, competitionNation, daysBetween, longDate, shortDate } from '../lib/format'
import SeasonSummary from './SeasonSummary'

const OUTCOME_COLOR = { W: 'teal', D: 'gray', L: 'red' } as const
const MAX_DAYS = 400 // api/sim.py

const STOP_TEXT: Record<string, string> = {
  date: 'Reached the date.',
  season_end: 'The season is over.',
  cancelled: 'Stopped.',
  offer: 'A club has made an offer for one of your players: answer it on the Transfers page.',
  abandoned: 'Another career was loaded.',
  error: 'Something went wrong.',
}

function Results({ results }: { results: SimResult[] }) {
  return (
    <Stack gap={4}>
      {[...results].reverse().map((r) => (
        <Group key={r.fixture_id} gap="xs" wrap="nowrap">
          <Badge color={OUTCOME_COLOR[r.outcome]} w={28} px={0}>
            {r.outcome}
          </Badge>
          <Text size="sm" c="dimmed" w={52}>
            {shortDate(r.date)}
          </Text>
          <Text size="sm">
            {r.home} {r.home_goals}–{r.away_goals} {r.away}
          </Text>
        </Group>
      ))}
    </Stack>
  )
}

// "Sim to…": moves the career on to a chosen day, playing the user's matches instantly, with
// progress and a Stop button meanwhile and a summary at the end.
export default function SimToDate({ career, matchToday }: { career: Career; matchToday: boolean }) {
  const status = useSimStatus()
  const start = useStartSim()
  const stop = useStopSim()
  const client = useQueryClient()
  const [picking, setPicking] = useState(false)
  const [picked, setPicked] = useState('')
  const [summary, setSummary] = useState<SimStatus | null>(null)
  // The news (and at the season's end, how it went) gets a window of its own, after the
  // results: closing one never takes the other with it.
  const [news, setNews] = useState<SimStatus | null>(null)
  const closeSummary = () => {
    if (summary && (summary.messages.length > 0 || summary.season_final)) setNews(summary)
    setSummary(null)
  }
  const wasRunning = useRef(false)
  const job = status.data ?? null
  const running = job?.running ?? false

  // When a sim this page watched ends: refresh everything and show what happened.
  useEffect(() => {
    if (wasRunning.current && !running && job) {
      setSummary(job)
      void client.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'world-leagues' && q.queryKey[0] !== 'sim' })
    }
    wasRunning.current = running
  }, [running, job, client])

  const go = (until: string) => {
    setPicking(false)
    start.mutate(until)
  }
  const tomorrow = addDays(career.date, 1)
  const latest = addDays(career.date, MAX_DAYS)
  // The season's calendar ends after its play-offs; the rollover on that day stops the sim.
  const endOfSeason = addDays(career.season_end, 1)

  let progress = 0
  if (job) {
    const total = daysBetween(job.start, job.until <= career.season_end ? job.until : career.season_end)
    progress = total > 0 ? Math.min(100, (100 * daysBetween(job.start, job.date)) / total) : 100
  }

  return (
    <>
      <Menu position="bottom-end" withinPortal>
        <Menu.Target>
          <Button size="sm" variant="light" loading={start.isPending || running}>
            Sim to…
          </Button>
        </Menu.Target>
        <Menu.Dropdown>
          {matchToday && <Menu.Label>Today&apos;s match is played instantly</Menu.Label>}
          <Menu.Item onClick={() => go(addDays(career.date, 7))}>One week</Menu.Item>
          <Menu.Item onClick={() => go(addMonths(career.date, 1))}>One month</Menu.Item>
          <Menu.Item onClick={() => go(endOfSeason)}>End of season</Menu.Item>
          <Menu.Divider />
          <Menu.Item
            onClick={() => {
              setPicked(addDays(career.date, 14))
              setPicking(true)
            }}
          >
            Choose a date…
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>

      {start.error && (
        <Text c="red" size="sm">
          {start.error.message}
        </Text>
      )}

      <Modal opened={picking} onClose={() => setPicking(false)} title="Sim to a date" centered>
        <Stack>
          <TextInput
            type="date"
            label="Up to (that day's matches are left for you)"
            value={picked}
            min={tomorrow}
            max={latest}
            onChange={(e) => setPicked(e.currentTarget.value)}
          />
          <Text size="xs" c="dimmed">
            Your matches before then are played instantly. It stops early at the end of the season.
          </Text>
          <Button disabled={!picked || picked < tomorrow || picked > latest} onClick={() => go(picked)}>
            Sim
          </Button>
        </Stack>
      </Modal>

      <Modal opened={running} onClose={() => undefined} withCloseButton={false} closeOnClickOutside={false} closeOnEscape={false} centered title="Simulating">
        {job && (
          <Stack>
            <Text size="sm">
              To {longDate(job.until <= career.season_end ? job.until : career.season_end)}
              {job.until > career.season_end ? ' (end of season)' : ''}
            </Text>
            <Progress value={progress} animated aria-label="Simulation progress" />
            <Text size="sm" c="dimmed">
              {longDate(job.date)} · {job.results.length} {job.results.length === 1 ? 'match' : 'matches'} played
            </Text>
            <ScrollArea.Autosize mah={220}>
              <Results results={job.results} />
            </ScrollArea.Autosize>
            <Button color="red" variant="light" loading={stop.isPending} onClick={() => stop.mutate()}>
              Stop
            </Button>
          </Stack>
        )}
      </Modal>

      <Modal opened={summary !== null} onClose={closeSummary} centered title="Simulation finished">
        {summary && (
          <Stack>
            <Text size="sm">
              {STOP_TEXT[summary.stop ?? ''] ?? ''} Now {longDate(summary.date)}.
              {summary.error ? ` ${summary.error}` : ''}
            </Text>
            {summary.results.length > 0 && (
              <ScrollArea.Autosize mah={300}>
                <Results results={summary.results} />
              </ScrollArea.Autosize>
            )}
            <Button onClick={closeSummary}>
              {summary.stop === 'season_end' ? 'Season summary' : summary.messages.length > 0 ? 'News' : 'OK'}
            </Button>
          </Stack>
        )}
      </Modal>

      <Modal
        opened={news !== null && summary === null}
        onClose={() => setNews(null)}
        centered
        size="lg"
        scrollAreaComponent={ScrollArea.Autosize}
        title={news?.stop === 'season_end' ? 'Season summary' : 'News'}
      >
        {news && (
          <Stack>
            {news.season_final ? (
              // The summary has its own sections for the season-end news.
              <SeasonSummary
                final={news.season_final}
                userClubId={career.club.id}
                userNation={career.competition ? competitionNation(career.competition) : undefined}
                onNavigate={() => setNews(null)}
              />
            ) : (
              news.messages.length > 0 && (
                <ScrollArea.Autosize mah={360}>
                  <List spacing={4} size="sm">
                    {news.messages.map((m, i) => (
                      <List.Item key={`${i}-${m}`}>{m}</List.Item>
                    ))}
                  </List>
                </ScrollArea.Autosize>
              )
            )}
            <Button onClick={() => setNews(null)}>OK</Button>
          </Stack>
        )}
      </Modal>
    </>
  )
}
