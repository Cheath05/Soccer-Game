// US college soccer helpers (W9c): a college coach's career and recruiting.

/** A program's tier (1, a national power, to 5) as stars: five for tier 1. */
export const tierStars = (tier: number) => '★'.repeat(Math.max(1, 6 - tier))

/** A recruit's star rating as stars. */
export const stars = (n: number) => '★'.repeat(n)

/** A scholarship share as text: "Full", "60%", or "Walk-on". */
export function scholarshipLabel(share: number): string {
  if (share >= 0.995) return 'Full'
  if (share <= 0.001) return 'Walk-on'
  return `${Math.round(share * 100)}%`
}

export const CLASS_NAMES: Record<string, string> = { Fr: 'Freshman', So: 'Sophomore', Jr: 'Junior', Sr: 'Senior' }
