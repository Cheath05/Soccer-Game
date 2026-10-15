import type { Career, EuropeZone, Fixture } from '../../api/types'
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
