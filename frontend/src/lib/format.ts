import { useSyncExternalStore } from 'react'

// Money is kept in euros everywhere; the player picks the currency it's shown in (dollars until
// they choose another). The rates are fixed (display only), so a figure never changes with a
// market.
export type Currency = 'EUR' | 'GBP' | 'USD'
export const CURRENCIES: Record<Currency, { symbol: string; perEuro: number; label: string }> = {
  USD: { symbol: '$', perEuro: 1.1, label: '$' },
  EUR: { symbol: '€', perEuro: 1, label: '€' },
  GBP: { symbol: '£', perEuro: 0.85, label: '£' },
}
const CURRENCY_KEY = 'footsim.currency'
const listeners = new Set<() => void>()
let shown: Currency = readCurrency()

function readCurrency(): Currency {
  try {
    const stored = localStorage.getItem(CURRENCY_KEY)
    return stored === 'EUR' || stored === 'GBP' ? stored : 'USD'
  } catch {
    return 'USD'
  }
}

export function setCurrency(next: Currency) {
  shown = next
  try {
    localStorage.setItem(CURRENCY_KEY, next)
  } catch {
    // private window: the choice lasts for this visit
  }
  listeners.forEach((listener) => listener())
}

/** The currency money is shown in; re-renders the caller when the player changes it. */
export function useCurrency(): Currency {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    () => shown,
  )
}

/** An amount in euros, shown in the chosen currency: €1.2B, −£35M, $850K. */
export function money(eur: number): string {
  const { symbol, perEuro } = CURRENCIES[shown]
  const value = eur * perEuro
  const sign = value < 0 ? '−' : ''
  const size = Math.abs(value)
  if (size >= 1_000_000_000) return `${sign}${symbol}${(size / 1_000_000_000).toFixed(size >= 10_000_000_000 ? 1 : 2)}B`
  if (size >= 1_000_000) return `${sign}${symbol}${(size / 1_000_000).toFixed(size >= 10_000_000 ? 0 : 1)}M`
  if (size >= 1_000) return `${sign}${symbol}${Math.round(size / 1_000)}K`
  return `${sign}${symbol}${Math.round(size)}`
}

export function wage(eurPerWeek: number): string {
  return `${money(eurPerWeek)}/wk`
}

/** An amount typed in the shown currency, in euros (what the game keeps): $11M is €10M. */
export function toEuros(amountShown: number): number {
  return Math.round(amountShown / CURRENCIES[shown].perEuro)
}

export function longDate(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString('en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

// Calendar arithmetic on ISO dates (YYYY-MM-DD), free of time zones.
export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

export function addMonths(iso: string, months: number): string {
  const d = new Date(`${iso}T12:00:00Z`)
  const day = d.getUTCDate()
  d.setUTCDate(1)
  d.setUTCMonth(d.getUTCMonth() + months)
  const last = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate()
  d.setUTCDate(Math.min(day, last))
  return d.toISOString().slice(0, 10)
}

export function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T12:00:00Z`) - Date.parse(`${from}T12:00:00Z`)) / 86_400_000)
}

export function shortDate(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

/** An ISO date as its month and year: Jul 2027. */
export function monthYear(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
}

const SPECIAL_LABELS: Record<string, string> = {
  off_ball: 'Off the Ball',
  def_positioning: 'Def. Positioning',
  gk_command_of_area: 'Command of Area',
  gk_one_on_ones: 'One-on-Ones',
  gk_rushing_out: 'Rushing Out',
  free_kicks: 'Free Kicks',
  heading_accuracy: 'Heading',
  natural_fitness: 'Natural Fitness',
}

export function attributeLabel(key: string): string {
  if (SPECIAL_LABELS[key]) return SPECIAL_LABELS[key]
  const words = key.replace(/^gk_/, '').split('_')
  return words.map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}

export function ratingColor(value: number): string {
  if (value >= 85) return 'teal.7'
  if (value >= 75) return 'green.6'
  if (value >= 65) return 'lime.7'
  if (value >= 55) return 'yellow.7'
  if (value >= 45) return 'orange.6'
  return 'red.6'
}

export function matchRatingColor(value: number): string {
  if (value >= 8) return 'teal.7'
  if (value >= 7) return 'green.6'
  if (value >= 6.3) return 'lime.7'
  if (value >= 5.5) return 'orange.6'
  return 'red.6'
}

export function score(f: { home_goals: number | null; away_goals: number | null; home_pens: number | null; away_pens: number | null; extra_time: boolean }): string {
  if (f.home_goals === null || f.away_goals === null) return 'v'
  let text = `${f.home_goals} – ${f.away_goals}`
  if (f.extra_time) text += ' (aet)'
  if (f.home_pens !== null && f.away_pens !== null) text += ` (${f.home_pens}–${f.away_pens} pens)`
  return text
}

export function stageLabel(stage: string, round: number, tie: string | null, leg: number | null, stageName?: string | null): string {
  if (stage === 'league') return `Matchday ${round}`
  const name = stageName ?? (tie?.startsWith('F') ? 'Play-off final' : tie?.startsWith('SF') ? 'Play-off semi-final' : 'Play-off')
  return leg ? `${name}, leg ${leg}` : name
}

export const POSITION_ORDER = ['GK', 'RB', 'RWB', 'CB', 'LB', 'LWB', 'DM', 'CM', 'AM', 'RM', 'LM', 'RW', 'LW', 'ST']

export function positionColor(position: string): string {
  if (position === 'GK') return 'yellow'
  if (['CB', 'LB', 'RB', 'LWB', 'RWB'].includes(position)) return 'blue'
  if (['DM', 'CM', 'AM', 'LM', 'RM'].includes(position)) return 'green'
  return 'red'
}

/** How a club's league season ended, for badges in tables and histories. */
export const OUTCOMES: Record<string, { label: string; color: string }> = {
  champion: { label: 'Champions', color: 'yellow' },
  promoted: { label: 'Promoted', color: 'teal' },
  playoff_winner: { label: 'Play-off winners', color: 'teal' },
  playoffs: { label: 'Play-offs', color: 'blue' },
  relegated: { label: 'Relegated', color: 'red' },
}

export function ordinal(n: number): string {
  const suffix = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th'
  return `${n}${suffix}`
}

const NATION_NAMES: Record<string, string> = {
  ENG: 'England',
  ESP: 'Spain',
  ITA: 'Italy',
  GER: 'Germany',
  FRA: 'France',
  POR: 'Portugal',
  NED: 'Netherlands',
  SCO: 'Scotland',
  BEL: 'Belgium',
  TUR: 'Turkey',
  KSA: 'Saudi Arabia',
  USA: 'United States',
}

/** A nation code as its name (ENG is England). A code with no name stays as it is. */
export function nationName(code: string): string {
  return NATION_NAMES[code] ?? code
}

/** The nation a league belongs to: its `nation` code, or for a server that predates the field
 * the first three letters of its key (ENG1 is ENG). */
export function competitionNation(c: { key: string; nation?: string }): string {
  return c.nation || c.key.slice(0, 3)
}

/** The countries listed first wherever one is picked, in this order. */
export const BIG_FIVE = ['ENG', 'ESP', 'ITA', 'GER', 'FRA']

/** Leagues grouped by nation, the big five first (England, Spain, Italy, Germany, France) and then the rest by name, each nation's leagues in tier order. */
export function groupByNation<T extends { key: string; tier: number; nation?: string }>(leagues: T[]): { code: string; name: string; leagues: T[] }[] {
  const groups = new Map<string, T[]>()
  for (const league of leagues) {
    const code = competitionNation(league)
    const group = groups.get(code)
    if (group) group.push(league)
    else groups.set(code, [league])
  }
  const rank = (code: string) => (BIG_FIVE.includes(code) ? BIG_FIVE.indexOf(code) : BIG_FIVE.length)
  return [...groups]
    .map(([code, list]) => ({ code, name: nationName(code), leagues: list.sort((a, b) => a.tier - b.tier || a.key.localeCompare(b.key)) }))
    .sort((a, b) => rank(a.code) - rank(b.code) || a.name.localeCompare(b.name))
}

/** The board's confidence colour: green when pleased, red when unhappy. */
export function confidenceColor(confidence: number | null): string {
  if (confidence === null) return 'gray'
  if (confidence >= 65) return 'green'
  if (confidence >= 45) return 'teal'
  if (confidence >= 30) return 'orange'
  return 'red'
}
