import type { Career, EuropeZone, Fixture, QualifyingPath, QualifyingRound } from '../../api/types'
import { shortDate } from '../../lib/format'

/** The league-phase zones: the colour of a row and its legend entry. */
export const ZONES: Record<EuropeZone, { color: string; label: string }> = {
  round_of_16: { color: 'teal', label: 'Round of 16' },
  playoff: { color: 'blue', label: 'Knockout play-off' },
  out: { color: 'gray', label: 'Out' },
}

/** Tue 15 Sep */
export function dayDate(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })
}

/** 18 Aug and 25 Aug */
export function dateList(dates: string[]): string {
  const days = dates.map(shortDate)
  return days.length > 1 ? `${days.slice(0, -1).join(', ')} and ${days[days.length - 1]}` : (days[0] ?? '')
}

/** Where a fixture's score leads: its match report once played, the match day page when it is
 * your match today, nowhere otherwise. */
export function fixtureTarget(f: Fixture, career: Career | undefined): 'report' | 'matchday' | null {
  if (f.status === 'played') return 'report'
  if (career?.next_fixture?.id === f.id && f.date === career.date) return 'matchday'
  return null
}

const ROUND_NAMES: Record<QualifyingRound, string> = {
  Q1: 'First qualifying round',
  Q2: 'Second qualifying round',
  Q3: 'Third qualifying round',
  PO: 'Play-off round',
}
const PATH_NAMES: Record<QualifyingPath, string> = { champions: 'Champions Path', league: 'League Path', main: 'Main Path' }

/** Sort order: first round first, then the champions path, the league path, the main path. */
export const ROUND_ORDER: QualifyingRound[] = ['Q1', 'Q2', 'Q3', 'PO']
export const PATH_ORDER: QualifyingPath[] = ['champions', 'league', 'main']

/** "Second qualifying round (Champions Path)" */
export function roundTitle(round: QualifyingRound, path?: QualifyingPath | null): string {
  return path ? `${ROUND_NAMES[round]} (${PATH_NAMES[path]})` : ROUND_NAMES[round]
}
