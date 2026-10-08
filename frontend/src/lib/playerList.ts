// The players of the list a visitor clicked a player from, in the order it was shown, so the player
// page can step to the previous and next one (and the squad's sort and filter are respected).
const KEY = 'footsim.playerList'

export function rememberPlayerList(ids: number[]) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(ids))
  } catch {
    // private window: the player page falls back to the club's squad order
  }
}

export function recallPlayerList(): number[] {
  try {
    const raw = sessionStorage.getItem(KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((x): x is number => typeof x === 'number') : []
  } catch {
    return []
  }
}
