import { useSyncExternalStore } from 'react'

import type { Nation } from '../api/types'

// Money is kept in euros everywhere; the player picks the currency it's shown in (dollars until
// they choose another), kept with the career. The rates are fixed (display only), so a figure
// never changes with a market, and match data/config/finance/finance.yaml `currencies`: the
// server quotes prices as round figures in the chosen currency, so what's shown is what's paid.
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

/** The currency shown now (outside React). */
export function shownCurrency(): Currency {
  return shown
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

/** One decimal, dropped when it's zero: 27.5, 28. */
function trimmed(n: number): string {
  return n.toFixed(1).replace(/\.0$/, '')
}

/** An amount in euros, shown in the chosen currency: €1.25B, −£35M, $27.5M, $850K. The server
 * writes amounts in its text the same way (world/money.py money_text). */
export function money(eur: number): string {
  const { symbol, perEuro } = CURRENCIES[shown]
  const value = eur * perEuro
  const sign = value < 0 ? '−' : ''
  const size = Math.abs(value)
  if (size >= 1_000_000_000) return `${sign}${symbol}${(size / 1_000_000_000).toFixed(size >= 10_000_000_000 ? 1 : 2)}B`
  if (size >= 999_950) return `${sign}${symbol}${trimmed(size / 1_000_000)}M`
  if (size >= 1_000) return `${sign}${symbol}${Math.round(size / 1_000)}K`
  return `${sign}${symbol}${Math.round(size)}`
}

/** A weekly wage, as exact as clubs write them: $2,550/wk, $85.5K/wk, $1.2M/wk. */
export function wage(eurPerWeek: number): string {
  const { symbol, perEuro } = CURRENCIES[shown]
  const size = Math.abs(eurPerWeek * perEuro)
  if (size >= 999_950) return `${money(eurPerWeek)}/wk`
  if (size >= 10_000) return `${symbol}${trimmed(size / 1_000)}K/wk`
  return `${symbol}${Math.round(size).toLocaleString('en-US')}/wk`
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

/** The aggregate of a two-legged tie in brackets: "(3 – 3 agg.)" when level, "(4 – 2 on agg.)"
 * when not. Home and away are the second leg's, like its score. */
export function aggText(home: number, away: number): string {
  return `(${home} – ${away}${home === away ? ' agg.' : ' on agg.'})`
}

/** A fixture's score: 2 – 1; a second leg adds the aggregate, extra time and penalties follow:
 * 2 – 1 (4 – 3 on agg.) (aet) (4–2 pens). */
export function score(f: { home_goals: number | null; away_goals: number | null; home_pens: number | null; away_pens: number | null; extra_time: boolean; agg_home?: number | null; agg_away?: number | null }): string {
  if (f.home_goals === null || f.away_goals === null) return 'v'
  let text = `${f.home_goals} – ${f.away_goals}`
  if (f.agg_home != null && f.agg_away != null) text += ` ${aggText(f.agg_home, f.agg_away)}`
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
  // The big five, the rest of UEFA's countries, then the likely ones from other continents. A code
  // not here is shown as the server names it (GET /api/world/nations).
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
  POL: 'Poland',
  ROU: 'Romania',
  SWE: 'Sweden',
  NOR: 'Norway',
  DEN: 'Denmark',
  SUI: 'Switzerland',
  AUT: 'Austria',
  IRL: 'Ireland',
  ISR: 'Israel',
  MDA: 'Moldova',
  ISL: 'Iceland',
  BIH: 'Bosnia and Herzegovina',
  ARM: 'Armenia',
  LVA: 'Latvia',
  KOS: 'Kosovo',
  KAZ: 'Kazakhstan',
  FRO: 'Faroe Islands',
  MLT: 'Malta',
  LTU: 'Lithuania',
  LIE: 'Liechtenstein',
  EST: 'Estonia',
  ALB: 'Albania',
  MNE: 'Montenegro',
  LUX: 'Luxembourg',
  GEO: 'Georgia',
  MKD: 'North Macedonia',
  BLR: 'Belarus',
  AND: 'Andorra',
  GIB: 'Gibraltar',
  SMR: 'San Marino',
  GRE: 'Greece',
  CZE: 'Czechia',
  UKR: 'Ukraine',
  CRO: 'Croatia',
  SRB: 'Serbia',
  CYP: 'Cyprus',
  HUN: 'Hungary',
  BUL: 'Bulgaria',
  AZE: 'Azerbaijan',
  SVK: 'Slovakia',
  SVN: 'Slovenia',
  FIN: 'Finland',
  WAL: 'Wales',
  NIR: 'Northern Ireland',
  RUS: 'Russia',
  KSA: 'Saudi Arabia',
  USA: 'United States',
  MEX: 'Mexico',
  CAN: 'Canada',
  BRA: 'Brazil',
  ARG: 'Argentina',
  JPN: 'Japan',
  KOR: 'South Korea',
  CHN: 'China',
  AUS: 'Australia',
}

// Other names a country goes by, for searching only ("holland" finds the Netherlands).
const NATION_ALIASES: Record<string, string> = {
  ENG: 'UK United Kingdom Britain',
  SCO: 'UK United Kingdom Britain',
  WAL: 'UK United Kingdom Britain',
  NIR: 'UK United Kingdom Britain',
  IRL: 'Republic of Ireland Eire',
  GER: 'Deutschland',
  ESP: 'Espana',
  NED: 'Holland',
  CZE: 'Czech Republic',
  TUR: 'Turkiye',
  MKD: 'Macedonia',
  BIH: 'Bosnia',
  FRO: 'Faroes',
  KSA: 'Saudi',
  KOR: 'Korea',
  USA: 'America United States of America US',
}

/** A nation code as its name (ENG is England): ours if we have one, else `fallback` (the name the
 * server sent), else the code itself. */
export function nationName(code: string, fallback?: string): string {
  return NATION_NAMES[code] ?? fallback ?? code
}

/** What a search for a country is matched against: its code, name and the other names it goes by. */
export function nationSearchText(code: string, name: string): string {
  return `${code} ${name} ${NATION_ALIASES[code] ?? ''}`
}

const UNACCENTED: Record<string, string> = { ø: 'o', æ: 'ae', œ: 'oe', ß: 'ss', ł: 'l', đ: 'd', ð: 'd', þ: 'th', ı: 'i' }

/** Text in lower case with its accents taken off, for comparing what someone typed with a name:
 * "Süper" and "super" are the same, and so are "Brøndby" and "brondby". */
export function foldText(text: string): string {
  return text
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
    .replace(/[øæœßłđðþı]/g, (c) => UNACCENTED[c] ?? c)
}

/** Whether every word typed is somewhere in the text, accents and capitals ignored. Typing nothing matches everything. */
export function matchesSearch(text: string, typed: string): boolean {
  const words = foldText(typed).split(/\s+/).filter(Boolean)
  const folded = foldText(text)
  return words.every((word) => folded.includes(word))
}

/** The nation a league belongs to: its `nation` code, or for a server that predates the field
 * the first three letters of its key (ENG1 is ENG). */
export function competitionNation(c: { key: string; nation?: string }): string {
  return c.nation || c.key.slice(0, 3)
}

/** The countries that are always one tap away wherever one is picked, in this order. */
export const BIG_FIVE = ['ENG', 'ESP', 'ITA', 'GER', 'FRA']

/** Where a code stands among the big five (England first); the others come after them. */
export const bigFiveIndex = (code: string) => (BIG_FIVE.includes(code) ? BIG_FIVE.indexOf(code) : BIG_FIVE.length)

/** A country as a picker offers it. `continent` and `rank` are the server's, once it has answered. */
export interface NationChoice {
  code: string
  name: string
  continent?: string
  featured: boolean // one of the big five
  rank?: number
}

/** Nation codes as picker choices, named and listed in the server's order (UEFA's ranking, then the
 * other continents') or, before it has answered, with the big five first and then by name. */
export function nationChoices(codes: Iterable<string>, nations?: Nation[]): NationChoice[] {
  const known = new Map((nations ?? []).map((n) => [n.code, n]))
  return [...new Set(codes)]
    .map((code) => {
      const n = known.get(code)
      return { code, name: nationName(code, n?.name), continent: n?.continent, featured: n?.featured ?? BIG_FIVE.includes(code), rank: n?.rank }
    })
    .sort((a, b) => (a.rank ?? Number.MAX_SAFE_INTEGER) - (b.rank ?? Number.MAX_SAFE_INTEGER) || bigFiveIndex(a.code) - bigFiveIndex(b.code) || a.name.localeCompare(b.name))
}

/** Leagues grouped by nation in the order of `nationChoices` (pass the server's `nations` for its ranking), each nation's leagues in tier order. */
export function groupByNation<T extends { key: string; tier: number; nation?: string; name?: string }>(
  leagues: T[],
  nations?: Nation[],
): (NationChoice & { leagues: T[] })[] {
  const groups = new Map<string, T[]>()
  for (const league of leagues) {
    const code = competitionNation(league)
    const group = groups.get(code)
    if (group) group.push(league)
    else groups.set(code, [league])
  }
  return nationChoices(groups.keys(), nations).map((n) => ({
    ...n,
    leagues: (groups.get(n.code) ?? []).sort((a, b) => a.tier - b.tier || a.key.localeCompare(b.key)),
  }))
}

/** The board's confidence colour: green when pleased, red when unhappy. */
export function confidenceColor(confidence: number | null): string {
  if (confidence === null) return 'gray'
  if (confidence >= 65) return 'green'
  if (confidence >= 45) return 'teal'
  if (confidence >= 30) return 'orange'
  return 'red'
}
