import type { Tactics } from '../api/types'

/** A saved line-up: pitch slot ids (and SUB1..SUBn for the bench) to player ids. */
export type Lineup = Record<string, number>

export const subKey = (n: number) => `SUB${n}`

/** The line-up as the tactics screen shows it now: every starter in his slot, and the bench in order. */
export function fullLineup(t: Tactics): Lineup {
  const lineup: Lineup = {}
  t.starters.forEach((s) => {
    if (s.slot) lineup[s.slot] = s.player_id
  })
  t.bench.forEach((b, i) => {
    lineup[subKey(i + 1)] = b.player_id
  })
  return lineup
}

/** Where a player is in a line-up (a slot id or a bench place), or undefined when he is a reserve. */
export function placeOf(lineup: Lineup, playerId: number): string | undefined {
  return Object.keys(lineup).find((k) => lineup[k] === playerId)
}

/** Put a player in a place (a slot or a bench place). Whoever was there takes the place he left, or becomes a reserve if he was one. */
export function swapInto(lineup: Lineup, playerId: number, place: string): Lineup {
  const next = { ...lineup }
  const occupant = next[place]
  const from = placeOf(next, playerId)
  next[place] = playerId
  if (from !== undefined && from !== place) {
    if (occupant !== undefined) next[from] = occupant
    else delete next[from]
  }
  return next
}

/** The first bench place with nobody in it, if the bench isn't full. */
export function freeBenchPlace(lineup: Lineup, size: number): string | undefined {
  for (let n = 1; n <= size; n++) if (lineup[subKey(n)] === undefined) return subKey(n)
  return undefined
}
