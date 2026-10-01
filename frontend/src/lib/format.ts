export function money(eur: number): string {
  if (eur >= 1_000_000) return `€${(eur / 1_000_000).toFixed(eur >= 10_000_000 ? 0 : 1)}M`
  if (eur >= 1_000) return `€${Math.round(eur / 1_000)}K`
  return `€${eur}`
}

export function wage(eurPerWeek: number): string {
  return `${money(eurPerWeek)}/wk`
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

export function stageLabel(stage: string, round: number, tie: string | null, leg: number | null): string {
  if (stage === 'league') return `Matchday ${round}`
  const name = tie?.startsWith('F') ? 'Play-off final' : tie?.startsWith('SF') ? 'Play-off semi-final' : 'Play-off'
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
