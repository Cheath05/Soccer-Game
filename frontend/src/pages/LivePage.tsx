import {
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Checkbox,
  Group,
  Progress,
  ScrollArea,
  SegmentedControl,
  Select,
  Stack,
  Table,
  Tabs,
  Text,
  Title,
} from '@mantine/core'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useCallback, useEffect, useRef, useState } from 'react'

import { PITCH_LENGTH, PITCH_WIDTH, TEAM_COLORS, drawFrame, drawPitch, interpolate, toSnapshot } from '../match-viewer/draw'
import type { PlayerInfo, Snapshot } from '../match-viewer/draw'

interface FeedItem {
  t: number
  minute: number
  type: string
  team: number | null
  text: string
}

interface BenchPlayer {
  player_id: number
  name: string
  number: number
  position: string
}

interface LiveState {
  teams: { name: string; club_id: number }[]
  userTeam: number
  score: [number, number]
  minute: number
  period: number
  paused: boolean
  speed: number
  mode: string
  finished: boolean
  subsLeft: [number, number]
  lineup: PlayerInfo[]
  bench: BenchPlayer[][]
  formation: string[]
  formations: { key: string; name: string }[]
  instructions: Record<string, string>[]
  instructionOptions: { key: string; label: string; options: string[] }[]
  autoSubs: boolean[]
  stats: Record<string, number[]>
  feed: FeedItem[]
}

const SPEEDS = ['1', '2', '4', '8', '16', '32']
const IMPORTANT = new Set(['goal', 'red', 'yellow', 'penalty', 'sub', 'injury', 'half_time', 'full_time', 'penalties'])
const STAT_LABELS: Record<string, string> = {
  possession: 'Possession %',
  shots: 'Shots',
  on_target: 'On target',
  xg: 'Expected goals',
  passes: 'Passes',
  pass_pct: 'Pass accuracy %',
  corners: 'Corners',
  fouls: 'Fouls',
}

export default function LivePage() {
  const { fixtureId } = useParams({ from: '/live/$fixtureId' })
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const boxRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const buffer = useRef<Snapshot[]>([])
  const playhead = useRef<number | null>(null)
  const liveRef = useRef<LiveState | null>(null)
  const [live, setLive] = useState<LiveState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ended, setEnded] = useState<[number, number] | null>(null)
  const [showNames, setShowNames] = useState(true)
  const [subOut, setSubOut] = useState<string | null>(null)
  const [subIn, setSubIn] = useState<string | null>(null)
  const namesRef = useRef(showNames)

  useEffect(() => {
    namesRef.current = showNames
  }, [showNames])

  const send = useCallback((message: Record<string, unknown>) => {
    wsRef.current?.send(JSON.stringify(message))
  }, [])

  // WebSocket: receive frames and state from the engine.
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${protocol}://${window.location.host}/api/fixtures/${fixtureId}/live`)
    wsRef.current = ws
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data as string)
      if (msg.type === 'error') {
        setError(msg.message)
        return
      }
      if (msg.type === 'end') {
        setEnded(msg.score)
        if (liveRef.current) {
          const done = { ...liveRef.current, score: msg.score, stats: msg.stats ?? liveRef.current.stats, finished: true, paused: true }
          liveRef.current = done
          setLive(done)
        }
        void queryClient.invalidateQueries()
        return
      }
      const previous = liveRef.current
      if (msg.type === 'init') {
        const state: LiveState = {
          teams: msg.teams,
          userTeam: msg.user_team,
          score: msg.score,
          minute: msg.minute,
          period: msg.period,
          paused: msg.paused,
          speed: msg.speed,
          mode: msg.mode,
          finished: msg.finished,
          subsLeft: msg.subs_left,
          lineup: msg.lineup,
          bench: msg.bench,
          formation: msg.formation,
          formations: msg.formations,
          instructions: msg.instructions,
          instructionOptions: msg.instruction_options,
          autoSubs: msg.auto_subs,
          stats: msg.stats,
          feed: [...msg.feed].reverse(),
        }
        buffer.current = (msg.frames as number[][]).map(toSnapshot)
        playhead.current = buffer.current.length ? buffer.current[buffer.current.length - 1].t : null
        liveRef.current = state
        setLive(state)
        return
      }
      if (!previous) return
      const next: LiveState = {
        ...previous,
        score: msg.score,
        minute: msg.minute,
        period: msg.period,
        paused: msg.paused,
        speed: msg.speed,
        mode: msg.mode,
        finished: msg.finished,
        subsLeft: msg.subs_left,
      }
      if (msg.feed) next.feed = [...[...msg.feed].reverse(), ...previous.feed].slice(0, 200)
      if (msg.lineup) next.lineup = msg.lineup
      if (msg.bench) next.bench = msg.bench
      if (msg.formation) next.formation = msg.formation
      if (msg.stats) next.stats = msg.stats
      if (msg.instructions) next.instructions = msg.instructions
      if (msg.auto_subs) next.autoSubs = msg.auto_subs
      if (msg.lineup_stamina) {
        next.lineup = next.lineup.map((p) => ({ ...p, stamina: msg.lineup_stamina[p.index] }))
      }
      const frames = (msg.frames as number[][]).map(toSnapshot)
      if (frames.length) {
        const last = buffer.current[buffer.current.length - 1]
        const fresh = last ? frames.filter((f) => f.t > last.t) : frames
        if (msg.highlight || (last && fresh.length && fresh[0].t - last.t > 1)) {
          buffer.current = fresh // a new highlight or a skip: start playing from it
          playhead.current = fresh.length ? fresh[0].t : playhead.current
        } else {
          buffer.current.push(...fresh)
        }
      }
      liveRef.current = next
      setLive(next)
    }
    ws.onerror = () => setError('Lost connection to the match.')
    return () => ws.close()
  }, [fixtureId, queryClient])

  // Render loop: interpolate between engine frames at the chosen speed.
  useEffect(() => {
    let raf = 0
    let last = performance.now()
    const render = (now: number) => {
      const dt = (now - last) / 1000
      last = now
      const canvas = canvasRef.current
      const box = boxRef.current
      const state = liveRef.current
      const frames = buffer.current
      if (canvas && box && state) {
        const width = box.clientWidth
        const pad = 16
        const scale = (width - pad * 2) / PITCH_LENGTH
        const height = Math.round(PITCH_WIDTH * scale + pad * 2)
        if (canvas.width !== width || canvas.height !== height) {
          canvas.width = width
          canvas.height = height
        }
        const ctx = canvas.getContext('2d')
        if (ctx && frames.length) {
          const newest = frames[frames.length - 1].t
          const speed = state.mode === 'highlights' ? Math.min(state.speed, 4) : state.speed
          let pt = playhead.current ?? frames[0].t
          if (!state.paused) pt += dt * speed
          const lag = 0.25 * speed
          if (state.mode !== 'highlights' && pt < newest - Math.max(3, 4 * lag)) pt = newest - lag
          pt = Math.min(Math.max(pt, frames[0].t), newest)
          playhead.current = pt
          let k = 0
          while (k < frames.length - 2 && frames[k + 1].t < pt) k++
          const snap = frames.length > 1 ? interpolate(frames[k], frames[k + 1], pt) : frames[0]
          if (k > 40) buffer.current = frames.slice(k - 20) // keep a little history only
          drawPitch(ctx, scale, pad)
          drawFrame(ctx, scale, pad, snap, state.lineup, namesRef.current)
        } else if (ctx) {
          drawPitch(ctx, scale, pad)
        }
      }
      raf = requestAnimationFrame(render)
    }
    raf = requestAnimationFrame(render)
    return () => cancelAnimationFrame(raf)
  }, [])

  if (error) {
    return (
      <Stack>
        <Alert color="red">{error}</Alert>
        <Button variant="default" onClick={() => void navigate({ to: '/' })}>
          Back to dashboard
        </Button>
      </Stack>
    )
  }

  const user = live?.userTeam ?? 0
  const myPlayers = (live?.lineup ?? []).filter((p) => p.team === user && p.active)
  const myBench = live?.bench[user] ?? []
  const clock = live ? (live.finished || ended ? 'FT' : minuteLabel(live.minute, live.period)) : ''

  return (
    <Stack gap="sm">
      <Card withBorder padding="xs">
        <Group justify="space-between" wrap="nowrap">
          <Group gap="xs" wrap="nowrap" style={{ flex: 1 }}>
            <Box w={14} h={14} style={{ background: TEAM_COLORS[0].shirt, borderRadius: 3 }} />
            <Title order={4} lineClamp={1}>
              {live?.teams[0].name ?? '…'}
            </Title>
          </Group>
          <Stack gap={0} align="center">
            <Title order={2}>{live ? `${live.score[0]} – ${live.score[1]}` : ''}</Title>
            <Badge variant="light">{clock}</Badge>
          </Stack>
          <Group gap="xs" wrap="nowrap" justify="flex-end" style={{ flex: 1 }}>
            <Title order={4} lineClamp={1}>
              {live?.teams[1].name ?? '…'}
            </Title>
            <Box w={14} h={14} style={{ background: TEAM_COLORS[1].shirt, borderRadius: 3 }} />
          </Group>
        </Group>
      </Card>

      <Group align="start" gap="sm" wrap="wrap">
        <Stack gap="xs" style={{ flex: '3 1 560px', minWidth: 320 }}>
          <Box ref={boxRef} style={{ width: '100%', borderRadius: 8, overflow: 'hidden' }}>
            <canvas ref={canvasRef} style={{ display: 'block' }} />
          </Box>
          <Group gap="xs" wrap="wrap">
            <Button
              w={100}
              color={live?.paused ? 'teal' : 'gray'}
              disabled={!live || !!ended}
              onClick={() => send({ type: live?.paused ? 'resume' : 'pause' })}
            >
              {live?.paused ? 'Play' : 'Pause'}
            </Button>
            <SegmentedControl
              size="xs"
              value={String(live?.speed ?? 1)}
              onChange={(v) => send({ type: 'speed', value: Number(v) })}
              data={SPEEDS.map((s) => ({ value: s, label: `${s}×` }))}
            />
            <SegmentedControl
              size="xs"
              value={live?.mode === 'highlights' ? 'highlights' : 'full'}
              onChange={(v) => send({ type: 'mode', value: v })}
              data={[
                { value: 'full', label: 'Full match' },
                { value: 'highlights', label: 'Highlights' },
              ]}
            />
            <Button variant="default" disabled={!live || !!ended} onClick={() => send({ type: 'finish' })}>
              Skip to result
            </Button>
            <Checkbox label="Names" checked={showNames} onChange={(e) => setShowNames(e.currentTarget.checked)} />
          </Group>
          {ended && (
            <Alert color="teal" title="Full time">
              <Group>
                <Text>
                  {live?.teams[0].name} {ended[0]} – {ended[1]} {live?.teams[1].name}
                </Text>
                <Button size="xs" onClick={() => void navigate({ to: '/match/$fixtureId', params: { fixtureId } })}>
                  Match report
                </Button>
                <Button size="xs" variant="default" onClick={() => void navigate({ to: '/' })}>
                  Dashboard
                </Button>
              </Group>
            </Alert>
          )}
        </Stack>

        <Card withBorder padding="xs" style={{ flex: '1 1 320px', minWidth: 300 }}>
          <Tabs defaultValue="feed">
            <Tabs.List grow>
              <Tabs.Tab value="feed">Commentary</Tabs.Tab>
              <Tabs.Tab value="stats">Stats</Tabs.Tab>
              <Tabs.Tab value="tactics">Tactics</Tabs.Tab>
              <Tabs.Tab value="subs">Subs</Tabs.Tab>
            </Tabs.List>

            <Tabs.Panel value="feed" pt="xs">
              <ScrollArea h={430}>
                <Stack gap={4}>
                  {(live?.feed ?? []).map((f, i) => (
                    <Text key={`${f.t}-${i}`} size="sm" fw={IMPORTANT.has(f.type) ? 700 : 400} c={f.type === 'goal' ? 'teal' : undefined}>
                      <Text span c="dimmed" size="xs">
                        {f.minute}&apos;{' '}
                      </Text>
                      {f.team !== null && (
                        <Box
                          component="span"
                          display="inline-block"
                          w={8}
                          h={8}
                          mr={6}
                          style={{ background: TEAM_COLORS[f.team].shirt, borderRadius: 2 }}
                        />
                      )}
                      {f.text}
                    </Text>
                  ))}
                </Stack>
              </ScrollArea>
            </Tabs.Panel>

            <Tabs.Panel value="stats" pt="xs">
              <Stack gap={6}>
                {live &&
                  Object.entries(STAT_LABELS).map(([key, label]) => {
                    const [h, a] = live.stats[key] ?? [0, 0]
                    const total = h + a || 1
                    return (
                      <div key={key}>
                        <Group justify="space-between">
                          <Text size="sm" fw={600}>
                            {h}
                          </Text>
                          <Text size="xs" c="dimmed">
                            {label}
                          </Text>
                          <Text size="sm" fw={600}>
                            {a}
                          </Text>
                        </Group>
                        <Progress.Root size="sm">
                          <Progress.Section value={(100 * h) / total} color={TEAM_COLORS[0].shirt} />
                          <Progress.Section value={(100 * a) / total} color={TEAM_COLORS[1].shirt} />
                        </Progress.Root>
                      </div>
                    )
                  })}
              </Stack>
            </Tabs.Panel>

            <Tabs.Panel value="tactics" pt="xs">
              {live && (
                <Stack gap="xs">
                  <Select
                    label="Formation"
                    data={live.formations.map((f) => ({ value: f.key, label: f.name }))}
                    value={live.formation[user]}
                    onChange={(v) => v && send({ type: 'formation', key: v })}
                    allowDeselect={false}
                  />
                  {live.instructionOptions.map((ins) => (
                    <div key={ins.key}>
                      <Text size="xs" c="dimmed">
                        {ins.label}
                      </Text>
                      <SegmentedControl
                        fullWidth
                        size="xs"
                        value={live.instructions[user][ins.key]}
                        onChange={(v) => send({ type: 'instruction', key: ins.key, value: v })}
                        data={ins.options}
                      />
                    </div>
                  ))}
                  <Text size="xs" c="dimmed">
                    Changes apply immediately: watch the shape change on the pitch.
                  </Text>
                </Stack>
              )}
            </Tabs.Panel>

            <Tabs.Panel value="subs" pt="xs">
              {live && (
                <Stack gap="xs">
                  <Group justify="space-between">
                    <Text size="sm">Substitutions left: {live.subsLeft[user]}</Text>
                    <Checkbox
                      label="Assistant makes subs"
                      checked={live.autoSubs[user]}
                      onChange={(e) => send({ type: 'auto_subs', value: e.currentTarget.checked })}
                    />
                  </Group>
                  <Select
                    label="Player off"
                    placeholder="Choose"
                    data={myPlayers.map((p) => ({
                      value: String(p.player_id),
                      label: `${p.number} ${p.name} (${p.position}) · ${p.stamina}%`,
                    }))}
                    value={subOut}
                    onChange={setSubOut}
                  />
                  <Select
                    label="Player on"
                    placeholder="Choose"
                    data={myBench.map((p) => ({ value: String(p.player_id), label: `${p.number} ${p.name} (${p.position})` }))}
                    value={subIn}
                    onChange={setSubIn}
                  />
                  <Button
                    disabled={!subOut || !subIn || live.subsLeft[user] <= 0}
                    onClick={() => {
                      send({ type: 'sub', out: Number(subOut), in: Number(subIn) })
                      setSubOut(null)
                      setSubIn(null)
                    }}
                  >
                    Make substitution
                  </Button>
                  <Table verticalSpacing={2}>
                    <Table.Tbody>
                      {myPlayers.map((p) => (
                        <Table.Tr key={p.index}>
                          <Table.Td w={28}>{p.number}</Table.Td>
                          <Table.Td>{p.name}</Table.Td>
                          <Table.Td w={40}>{p.position}</Table.Td>
                          <Table.Td w={90}>
                            <Progress value={p.stamina} size="sm" color={p.stamina > 75 ? 'teal' : p.stamina > 60 ? 'yellow' : 'red'} />
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Stack>
              )}
            </Tabs.Panel>
          </Tabs>
        </Card>
      </Group>
    </Stack>
  )
}

function minuteLabel(minute: number, period: number): string {
  const cap = period === 1 ? 45 : period === 2 ? 90 : period === 3 ? 105 : 120
  return minute > cap ? `${cap}+${minute - cap}'` : `${minute}'`
}
