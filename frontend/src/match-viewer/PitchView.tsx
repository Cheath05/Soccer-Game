// The 2D pitch: plays the engine's frames back at the match's rate (match seconds per real
// second), interpolating between them. It draws what the engine produced and nothing else.

import { Box } from '@mantine/core'
import { useEffect, useRef } from 'react'
import type { MouseEvent } from 'react'

import { PITCH_LENGTH, PITCH_WIDTH, debugAt, drawDebug, drawFrame, drawNetOverlay, drawPitch, interpolate, padFor } from './draw'
import type { Snapshot } from './draw'
import { findRelease, goalBall, inNetAt, restAt, startGoal } from './goal'
import type { GoalMoment } from './goal'
import type { GoalInfo } from './protocol'
import type { LiveMatch } from './useLiveMatch'

// What the picture is showing of a goal, for the banner and the scoreboard: the goal whose
// ball is in the net (the banner's), and the goal on its way that must not be counted yet.
export interface GoalView {
  banner: GoalInfo | null
  unseenT: number | null
}

interface Props {
  match: LiveMatch
  showNames: boolean
  debug?: boolean // draw the engine's intentions on top (?debug=1)
  selected: number | null
  onSelect: (index: number | null) => void
  onGoalView?: (view: GoalView) => void
}

const STEER = 4 // per second: how quickly the picture closes a gap to the server's timeline

export default function PitchView({ match, showNames, debug = false, selected, onSelect, onGoalView }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const boxRef = useRef<HTMLDivElement>(null)
  const scaleRef = useRef(1)
  const padRef = useRef(16)
  const layerRef = useRef<{ canvas: HTMLCanvasElement; key: string } | null>(null)
  const goalRef = useRef<GoalMoment | null>(null) // the goal being shown
  const lastGoalT = useRef(-1) // the goal last started, so one is never shown twice
  const infoRef = useRef<Map<number, GoalInfo>>(new Map())
  const viewRef = useRef<GoalView>({ banner: null, unseenT: null })
  const onGoalViewRef = useRef(onGoalView)
  const snapRef = useRef<Snapshot | null>(null)
  const namesRef = useRef(showNames)
  const selectedRef = useRef(selected)
  const debugRef = useRef(debug)

  useEffect(() => {
    namesRef.current = showNames
    selectedRef.current = selected
    debugRef.current = debug
    onGoalViewRef.current = onGoalView
  }, [showNames, selected, debug, onGoalView])

  useEffect(() => {
    let raf = 0
    let last = performance.now()
    const render = (now: number) => {
      const dt = Math.min(0.25, (now - last) / 1000)
      last = now
      const canvas = canvasRef.current
      const box = boxRef.current
      const state = match.liveRef.current
      const frames = match.buffer.current
      if (canvas && box && state) {
        const width = box.clientWidth
        // Room for the nets behind the goals; the pitch fills what is left.
        const scale = Math.min((width - 32) / PITCH_LENGTH, width / (PITCH_LENGTH + 2 * (2.8 + 0.2)))
        const pad = padFor(scale)
        scaleRef.current = scale
        padRef.current = pad
        const height = Math.round(PITCH_WIDTH * scale + pad * 2)
        const dpr = Math.min(3, window.devicePixelRatio || 1)
        if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
          canvas.width = Math.round(width * dpr)
          canvas.height = Math.round(height * dpr)
          canvas.style.width = `${width}px`
          canvas.style.height = `${height}px`
        }
        const ctx = canvas.getContext('2d')
        if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
        // The pitch is drawn once per size and copied in each frame.
        const layerKey = `${width}x${height}@${dpr}`
        if (ctx && layerRef.current?.key !== layerKey) {
          const layer = document.createElement('canvas')
          layer.width = canvas.width
          layer.height = canvas.height
          const lctx = layer.getContext('2d')
          if (lctx) {
            lctx.setTransform(dpr, 0, 0, dpr, 0, 0)
            drawPitch(lctx, scale, pad)
          }
          layerRef.current = { canvas: layer, key: layerKey }
        }
        const backdrop = () => {
          if (ctx && layerRef.current) ctx.drawImage(layerRef.current.canvas, 0, 0, width, height)
        }
        if (ctx && frames.length) {
          const newest = frames[frames.length - 1].t
          let pt = match.playhead.current ?? frames[0].t
          const sync = match.sync.current
          if (sync) {
            // Follow the server's timeline: it carries on from what's on screen through pauses
            // and speed changes, so the picture moves on smoothly and never skips ahead.
            let target = sync.shown + (sync.moving ? ((now - sync.wall) / 1000) * sync.rate : 0)
            // Stopped (a goal, a pause) a little ahead of us: run on to it at the match's rate
            // instead of easing in, which would take a second or more to cover the last bit.
            if (sync.moving) pt += dt * sync.rate
            else if (pt < target) pt = Math.min(pt + dt * sync.rate, target)
            if (sync.holdAt !== null) {
              // Stop on a goal rather than running past it before the server says to hold.
              target = Math.min(target, sync.holdAt)
              pt = Math.min(pt, sync.holdAt)
            }
            const gap = target - pt
            // Far out (a highlight, or a tab that was hidden): go straight there.
            if (Math.abs(gap) > Math.max(3, 2 * sync.rate)) pt = target
            else pt += gap * Math.min(1, dt * STEER)
          } else {
            // An older server: play on at the match's rate, staying a little behind the newest
            // frame and jumping ahead if we fall far behind.
            const rate = state.mode === 'highlights' ? Math.min(state.playRate, 18) : state.playRate
            if (!state.paused || state.finished || state.atBreak) pt += dt * rate
            const lag = 0.3 * rate
            if (state.mode !== 'highlights' && pt < newest - Math.max(3, 4 * lag)) pt = newest - lag
          }
          pt = Math.min(Math.max(pt, frames[0].t), newest)
          match.playhead.current = pt
          canvas.dataset.t = pt.toFixed(2) // the match time on screen, for the browser tests
          let k = 0
          while (k < frames.length - 2 && frames[k + 1].t < pt) k++
          let snap = frames.length > 1 ? interpolate(frames[k], frames[k + 1], pt) : frames[0]

          // A goal: when the picture reaches it, the ball is carried over the line into the
          // net and held there until the restart is shown. The banner waits for the ball.
          if (state.holding) infoRef.current.set(state.holding.t, state.holding)
          const upcoming = sync?.holdAt ?? state.holding?.t ?? null
          let goal = goalRef.current
          if (goal && (pt < goal.t - 0.5 || (goal.releaseT !== null && pt >= goal.releaseT && goal.u >= restAt(goal)))) {
            goal = goalRef.current = null // over, or the picture has gone back before it
          }
          if (upcoming !== null && Math.abs(upcoming - lastGoalT.current) > 0.05 && pt >= upcoming - 0.02) {
            goal = goalRef.current = startGoal(frames, upcoming)
            lastGoalT.current = upcoming
          } else if (goal) {
            goal.u += dt
          }
          if (goal && goal.releaseT === null) goal.releaseT = findRelease(goal, frames)
          if (goal && pt >= goal.t - 0.02 && (goal.releaseT === null || pt < goal.releaseT)) {
            snap = { ...snap, ball: goalBall(goal), owner: -1 }
          }
          const nearGoal = goal !== null && pt >= goal.t - 0.02 && (goal.releaseT === null || pt < goal.releaseT)
          let banner: GoalInfo | null = null
          let unseenT: number | null = null
          if (goal && goal.u < inNetAt(goal)) unseenT = goal.t
          else if (!goal && upcoming !== null && Math.abs(upcoming - lastGoalT.current) > 0.05) unseenT = upcoming
          if (goal && nearGoal && goal.u >= inNetAt(goal) && pt <= goal.t + 0.25) banner = infoRef.current.get(goal.t) ?? null
          const view = viewRef.current
          if (banner?.t !== view.banner?.t || unseenT !== view.unseenT) {
            viewRef.current = { banner, unseenT }
            onGoalViewRef.current?.(viewRef.current)
          }

          snapRef.current = snap
          // For the browser tests: the goal on screen and how long the picture has been on it.
          canvas.dataset.goal = goal ? `${goal.t}:${goal.u.toFixed(2)}${nearGoal ? ':held' : ''}` : ''
          canvas.dataset.holding = state.holding ? String(state.holding.t) : ''
          if (k > 60) match.buffer.current = frames.slice(k - 20) // keep a little history
          backdrop()
          drawFrame(ctx, scale, pad, snap, state.lineup, namesRef.current, selectedRef.current)
          if (nearGoal) drawNetOverlay(ctx, scale, pad)
          if (debugRef.current) {
            const dbg = debugAt(match.debugBuffer.current, pt)
            if (dbg) drawDebug(ctx, scale, pad, snap, dbg, state.lineup)
          }
        } else if (ctx) {
          backdrop()
        }
      }
      raf = requestAnimationFrame(render)
    }
    raf = requestAnimationFrame(render)
    return () => cancelAnimationFrame(raf)
  }, [match])

  const onClick = (event: MouseEvent<HTMLCanvasElement>) => {
    const snap = snapRef.current
    const state = match.liveRef.current
    if (!snap || !state) return
    const rect = event.currentTarget.getBoundingClientRect()
    const x = (event.clientX - rect.left - padRef.current) / scaleRef.current
    const y = (event.clientY - rect.top - padRef.current) / scaleRef.current
    let best: number | null = null
    let bestDistance = 3 // metres
    for (const p of state.lineup) {
      if (!p.active) continue
      const d = Math.hypot(snap.players[p.index * 2] - x, snap.players[p.index * 2 + 1] - y)
      if (d < bestDistance) {
        best = p.index
        bestDistance = d
      }
    }
    onSelect(best)
  }

  return (
    <Box
      ref={boxRef}
      style={{
        width: '100%',
        borderRadius: 14,
        overflow: 'hidden',
        background: '#174b2d',
        boxShadow: '0 1px 2px rgba(0,0,0,0.18), 0 8px 24px rgba(8,30,18,0.28)',
      }}
    >
      <canvas ref={canvasRef} style={{ display: 'block', cursor: 'pointer' }} onClick={onClick} />
    </Box>
  )
}
