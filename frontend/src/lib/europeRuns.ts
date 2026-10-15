import type { EuropeRun } from '../api/types'

/** A European run in words: "Winners!", "Runners-up", "out in the quarter-final", "Semi-final". */
export function europeText(run: EuropeRun): string {
  if (run.won) return 'Winners!'
  if (run.out && run.reached === 'Final') return 'Runners-up'
  return run.out ? `out in the ${run.reached.toLowerCase()}` : run.reached
}
