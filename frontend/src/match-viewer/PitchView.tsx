// The 2D pitch: plays the engine's frames back at the match's rate (match seconds per real
// second), interpolating between them. It draws what the engine produced and nothing else.

import { Box } from '@mantine/core'
import { useEffect, useRef } from 'react'
import type { MouseEvent } from 'react'

import { PITCH_LENGTH, PITCH_WIDTH, drawFrame, drawPitch, interpolate } from './draw'
import type { Snapshot } from './draw'
import type { LiveMatch } from './useLiveMatch'

interface Props {
  match: LiveMatch
  showNames: boolean
  selected: number | null
  onSelect: (index: number | null) => void
}

const PAD = 16
const HIGHLIGHT_RATE = 18 // match seconds per real second while replaying a highlight

export default function PitchView({ match, showNames, selected, onSelect }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const boxRef = useRef<HTMLDivElement>(null)
  const scaleRef = useRef(1)
  const snapRef = useRef<Snapshot | null>(null)
  const namesRef = useRef(showNames)
  const selectedRef = useRef(selected)

  useEffect(() => {
    namesRef.current = showNames
    selectedRef.current = selected
  }, [showNames, selected])

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
        const scale = (width - PAD * 2) / PITCH_LENGTH
        scaleRef.current = scale
        const height = Math.round(PITCH_WIDTH * scale + PAD * 2)
        if (canvas.width !== width || canvas.height !== height) {
          canvas.width = width
          canvas.height = height
        }
        const ctx = canvas.getContext('2d')
        if (ctx && frames.length) {
          const newest = frames[frames.length - 1].t
          const rate = state.mode === 'highlights' ? Math.min(state.rate, HIGHLIGHT_RATE) : state.rate
          let pt = match.playhead.current ?? frames[0].t
          // A pause freezes the picture; at half-time the last moments still play out.
          if (!state.paused || state.finished || state.atBreak) pt += dt * rate
          // Stay a little behind the newest frame, and catch up if we fall far behind.
          const lag = 0.3 * rate
          if (state.mode !== 'highlights' && pt < newest - Math.max(3, 4 * lag)) pt = newest - lag
          pt = Math.min(Math.max(pt, frames[0].t), newest)
          match.playhead.current = pt
          let k = 0
          while (k < frames.length - 2 && frames[k + 1].t < pt) k++
          const snap = frames.length > 1 ? interpolate(frames[k], frames[k + 1], pt) : frames[0]
          snapRef.current = snap
          if (k > 60) match.buffer.current = frames.slice(k - 20) // keep a little history
          drawPitch(ctx, scale, PAD)
          drawFrame(ctx, scale, PAD, snap, state.lineup, namesRef.current, selectedRef.current)
        } else if (ctx) {
          drawPitch(ctx, scale, PAD)
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
    const x = (event.clientX - rect.left - PAD) / scaleRef.current
    const y = (event.clientY - rect.top - PAD) / scaleRef.current
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
    <Box ref={boxRef} style={{ width: '100%', borderRadius: 8, overflow: 'hidden' }}>
      <canvas ref={canvasRef} style={{ display: 'block', cursor: 'pointer' }} onClick={onClick} />
    </Box>
  )
}
