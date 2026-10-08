import type { SheetEntry } from '../api/types'

/** The colour of the marker for how at home a starter is in his slot: none when natural. */
export function fitColor(entry: Pick<SheetEntry, 'position_fit'>): string | null {
  return entry.position_fit === 'out' ? 'red' : entry.position_fit === 'adjusted' ? 'orange' : null
}

export const signed = (n: number) => (n > 0 ? `+${n}` : `−${-n}`)

/** "ST 72 · OVR 78 (CM) · out of position at ST −5 · not fully fit (72%) −1": what a starter rates
 * in his slot and why it differs from his overall. */
export function breakdownText(entry: SheetEntry): string {
  const parts = [`${entry.position} ${entry.rating}`, `OVR ${entry.overall} (${entry.best_position})`]
  for (const a of entry.adjustments) parts.push(`${a.label} ${signed(a.delta)}`)
  return parts.join(' · ')
}
