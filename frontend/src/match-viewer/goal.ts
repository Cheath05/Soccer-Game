// The moment of a goal as the picture shows it. The engine ends the play the instant the ball
// crosses the line (the next thing it records is a dead ball a metre or so over the line, and
// then the kick-off spot), and the session holds the picture on that instant. Drawn as it is,
// the ball stops short of the line and the banner comes up before the goal. So the viewer
// carries the ball on, purely visually: from where it was along the way it was going, over the
// line, into the net and to rest there, and holds it in the net until the restart is shown.
// Nothing here is a football decision: the goal, its time and the ball's last positions all
// come from the engine.

import { PITCH_LENGTH, PITCH_WIDTH } from './draw'
import type { Snapshot } from './draw'

const MID_Y = PITCH_WIDTH / 2
const GOAL_HALF = 3.66
const REST_DEPTH = 1.2 // where the ball settles, behind the line
const SETTLE = 0.5 // real seconds the ball takes to come to rest in the net
const IN_NET = 0.2 // real seconds after crossing the line until the ball is well inside it

export interface GoalMoment {
  t: number // the match time of the goal: where the picture holds
  u: number // real seconds since the picture reached it
  line: number // x of the goal line the ball crosses
  from: [number, number, number] // the ball when the picture reached the goal
  cross: [number, number, number] // where it crosses the line
  rest: [number, number] // where it comes to rest in the net
  approach: number // real seconds from `from` to the line
  dead: [number, number] | null // the dead ball's spot in the frames after the goal
  releaseT: number | null // the first match time at which the engine's ball has left that spot
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

/** Real seconds from the picture reaching the goal until the ball is in the net (the banner
 * comes up then). */
export function inNetAt(m: GoalMoment): number {
  return m.approach + IN_NET
}

/** Real seconds until the ball has come to rest. */
export function restAt(m: GoalMoment): number {
  return m.approach + SETTLE
}

/** Start the goal moment for a goal at match time ``t``, from the frames the picture has. */
export function startGoal(frames: Snapshot[], t: number): GoalMoment | null {
  let p = -1
  for (let i = 0; i < frames.length && frames[i].t <= t + 1e-3; i++) p = i
  if (p < 0) return null
  const last = frames[p]
  const after = p + 1 < frames.length ? frames[p + 1] : null
  const line = last.ball[0] > PITCH_LENGTH / 2 ? PITCH_LENGTH : 0
  const dir = line > 0 ? 1 : -1
  // The ball as the picture draws it at the goal: the engine's own frame, or (when the frames
  // are far apart) the blend between the frames either side.
  let from: [number, number, number] = [...last.ball]
  if (after && last.t < t - 1e-3) {
    const k = clamp((t - last.t) / (after.t - last.t), 0, 1)
    from = [0, 1, 2].map((i) => last.ball[i] + (after.ball[i] - last.ball[i]) * k) as [number, number, number]
  }
  // Its velocity, from the frame before.
  let vx = 0
  let vy = 0
  let vz = 0
  let known = false
  if (p > 0 && last.t - frames[p - 1].t > 0 && last.t - frames[p - 1].t <= 0.4) {
    const dt = last.t - frames[p - 1].t
    vx = (last.ball[0] - frames[p - 1].ball[0]) / dt
    vy = (last.ball[1] - frames[p - 1].ball[1]) / dt
    vz = (last.ball[2] - frames[p - 1].ball[2]) / dt
    known = vx * dir > 2
  }
  const dead: [number, number] | null =
    after && Math.abs(after.ball[0] - line) <= 2.6 && after.t - t <= 0.6 ? [after.ball[0], after.ball[1]] : null
  const ahead = Math.max(0, (line - from[0]) * dir)
  let cy: number
  let cz: number
  if (known) {
    const tc = ahead / (vx * dir)
    cy = from[1] + vy * tc
    cz = from[2] + vz * tc
  } else {
    cy = dead ? dead[1] : from[1]
    cz = from[2]
  }
  const reach = GOAL_HALF - 0.5 // the ball is drawn well inside the posts
  cy = clamp(cy, MID_Y - reach, MID_Y + reach)
  cz = clamp(cz, 0.15, 2.3)
  const speed = known ? Math.hypot(vx, vy) : 18
  const distance = Math.hypot(line - from[0], cy - from[1])
  // The last stretch is shown at about half speed so the eye can follow it.
  const approach = clamp(distance / (0.5 * Math.max(speed, 8)), 0.14, 0.6)
  const drift = known ? clamp((vy / Math.max(speed, 1)) * 0.5, -0.5, 0.5) : 0
  const rest: [number, number] = [line + dir * REST_DEPTH, clamp(cy + drift, MID_Y - reach, MID_Y + reach)]
  return { t, u: 0, line, from, cross: [line, cy, cz], rest, approach, dead, releaseT: null }
}

/** Where the ball is drawn ``m.u`` real seconds into the goal: on towards the line, over it,
 * into the net and to rest there. */
export function goalBall(m: GoalMoment): [number, number, number] {
  const { from, cross, rest } = m
  if (m.u < m.approach) {
    const s = m.u / m.approach
    return [from[0] + (cross[0] - from[0]) * s, from[1] + (cross[1] - from[1]) * s, from[2] + (cross[2] - from[2]) * s]
  }
  const w = clamp((m.u - m.approach) / SETTLE, 0, 1)
  const e = 1 - Math.pow(1 - w, 2.6) // fast into the net, then easing to rest
  return [cross[0] + (rest[0] - cross[0]) * e, cross[1] + (rest[1] - cross[1]) * e, cross[2] * (1 - e)]
}

/** The first match time (after the goal) at which the engine's ball has left the dead-ball
 * spot, i.e. the restart is shown; null if the frames don't reach it yet. */
export function findRelease(m: GoalMoment, frames: Snapshot[]): number | null {
  if (m.dead === null) return m.t + 1
  const [dx, dy] = m.dead
  for (const f of frames) {
    if (f.t <= m.t + 0.05) continue
    if (Math.hypot(f.ball[0] - dx, f.ball[1] - dy) > 0.3) return f.t
  }
  return null
}
