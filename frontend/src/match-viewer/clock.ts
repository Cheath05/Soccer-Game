// The football clock as shown on the scoreboard (mirrors backend match/engine/clock.py).

const PERIOD_START_MINUTE: Record<number, number> = { 1: 0, 2: 45, 3: 90, 4: 105 }
const PERIOD_SECONDS: Record<number, number> = { 1: 2700, 2: 2700, 3: 900, 4: 900 }

function mmss(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds))
  return `${String(Math.floor(whole / 60)).padStart(2, '0')}:${String(whole % 60).padStart(2, '0')}`
}

// "52:17", or "45:00 +01:37" in added time.
export function formatClock(period: number, elapsed: number): string {
  const start = (PERIOD_START_MINUTE[period] ?? 0) * 60
  const regulation = PERIOD_SECONDS[period] ?? 2700
  if (elapsed < regulation) return mmss(start + elapsed)
  return `${mmss(start + regulation)} +${mmss(elapsed - regulation)}`
}

export function periodName(period: number, atBreak: boolean, finished: boolean): string {
  if (finished) return 'Full time'
  if (atBreak) return period === 1 ? 'Half-time' : period === 2 ? 'Before extra time' : 'Extra-time break'
  return period === 1 ? '1st half' : period === 2 ? '2nd half' : period === 3 ? 'Extra time' : 'Extra time, 2nd half'
}
