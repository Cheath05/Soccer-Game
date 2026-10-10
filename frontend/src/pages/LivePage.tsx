import { Alert, Box, Button, Card, Checkbox, Group, ScrollArea, SegmentedControl, Select, Stack, Tabs, Text } from '@mantine/core'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useState } from 'react'

import { useCareer } from '../api/hooks'

import GoalBanner from '../match-viewer/GoalBanner'
import HalfTimePanel from '../match-viewer/HalfTimePanel'
import PitchView from '../match-viewer/PitchView'
import type { GoalView } from '../match-viewer/PitchView'
import PlaybackControls from '../match-viewer/PlaybackControls'
import PlayerCard from '../match-viewer/PlayerCard'
import ScoreBar from '../match-viewer/ScoreBar'
import StatsPanel from '../match-viewer/StatsPanel'
import SubsPanel from '../match-viewer/SubsPanel'
import { TEAM_COLORS } from '../match-viewer/draw'
import { useLiveMatch } from '../match-viewer/useLiveMatch'

const IMPORTANT = new Set(['goal', 'red', 'yellow', 'penalty', 'sub', 'injury', 'half_time', 'full_time', 'penalties', 'added_time', 'period_start'])

export default function LivePage() {
  const { fixtureId } = useParams({ from: '/live/$fixtureId' })
  const navigate = useNavigate()
  const match = useLiveMatch(fixtureId)
  const { live, error, notice, ended, send } = match
  const [showNames, setShowNames] = useState(true)
  const [debug, setDebug] = useState(false)
  const debugAvailable = new URLSearchParams(window.location.search).get('debug') === '1'
  const [selected, setSelected] = useState<number | null>(null)
  // What the pitch shows of a goal (the ball in the net, or on its way): the banner and the
  // score and commentary follow it.
  const [goalView, setGoalView] = useState<GoalView>({ banner: null, unseenT: null })
  const career = useCareer()
  const fixture = career.data?.next_fixture
  const competition = fixture && String(fixture.id) === fixtureId ? (fixture.stage_name ? `${fixture.competition_name} · ${fixture.stage_name}` : fixture.competition_name) : null

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
  const playhead = match.playhead.current ?? 0
  // Commentary follows the picture: nothing is told before it has been seen.
  const feed = (live?.feed ?? []).filter(
    (f) =>
      live?.finished ||
      (f.t <= playhead + 0.5 && !(f.type === 'goal' && goalView.unseenT !== null && Math.abs(f.t - goalView.unseenT) < 0.01)),
  )
  const selectedStatus = selected !== null ? live?.status.players.find((p) => p.index === selected) : undefined

  return (
    <Stack gap="sm">
      <ScoreBar match={match} competition={competition} unseenGoalT={goalView.unseenT} />
      <Group align="start" gap="sm" wrap="wrap">
        <Stack gap="xs" style={{ flex: '3 1 560px', minWidth: 'min(320px, 100%)' }}>
          <Box pos="relative">
            <PitchView match={match} showNames={showNames} debug={debug} selected={selected} onSelect={setSelected} onGoalView={setGoalView} />
            <GoalBanner goal={goalView.banner} live={live} />
            {selectedStatus && (
              <Box pos="absolute" top={8} left={8}>
                <PlayerCard
                  player={selectedStatus}
                  onClose={() => setSelected(null)}
                  onRole={(role) => send({ type: 'role', player: selectedStatus.player_id, role })}
                />
              </Box>
            )}
            {live?.atBreak && !live.finished && (
              <Box pos="absolute" top={0} left={0} right={0} bottom={0} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <HalfTimePanel match={match} />
              </Box>
            )}
          </Box>
          <PlaybackControls match={match} showNames={showNames} onShowNames={setShowNames} />
          {debugAvailable && (
            <Checkbox
              size="xs"
              label="Debug overlay: team lines, targets, pressers and the ball carrier's options"
              checked={debug}
              onChange={(e) => {
                const on = e.currentTarget.checked
                setDebug(on)
                send({ type: 'debug', value: on })
              }}
            />
          )}
          {notice && (
            <Text size="sm" c="orange">
              {notice}
            </Text>
          )}
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

        <Card withBorder radius="lg" padding="xs" style={{ flex: '1 1 340px', minWidth: 'min(320px, 100%)' }}>
          <Tabs defaultValue="feed" variant="pills" radius="xl">
            <Tabs.List grow>
              <Tabs.Tab value="feed">Commentary</Tabs.Tab>
              <Tabs.Tab value="stats">Stats</Tabs.Tab>
              <Tabs.Tab value="tactics">Tactics</Tabs.Tab>
              <Tabs.Tab value="subs">Subs</Tabs.Tab>
            </Tabs.List>

            <Tabs.Panel value="feed" pt="xs">
              <ScrollArea h={430}>
                <Stack gap={4}>
                  {feed.map((f, i) => (
                    <Text key={`${f.t}-${i}`} size="sm" fw={IMPORTANT.has(f.type) ? 700 : 400} c={f.type === 'goal' ? 'teal' : undefined}>
                      <Text span c="dimmed" size="xs" style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {f.clock}{' '}
                      </Text>
                      {f.team !== null && (
                        <Box component="span" display="inline-block" w={8} h={8} mr={6} style={{ background: TEAM_COLORS[f.team].shirt, borderRadius: 2 }} />
                      )}
                      {f.text}
                    </Text>
                  ))}
                </Stack>
              </ScrollArea>
            </Tabs.Panel>

            <Tabs.Panel value="stats" pt="xs">
              {live && <StatsPanel stats={live.stats} />}
            </Tabs.Panel>

            <Tabs.Panel value="tactics" pt="xs">
              {live && (
                <Stack gap="xs">
                  <Checkbox
                    size="xs"
                    label="Assistant adjusts tactics to the score and the opponent"
                    checked={live.aiManager?.[user] ?? false}
                    onChange={(e) => send({ type: 'assistant', value: e.currentTarget.checked })}
                  />
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
                    Changes apply straight away: watch the shape change on the pitch. With the assistant on, your
                    choices become its plan and it adjusts from there.
                  </Text>
                </Stack>
              )}
            </Tabs.Panel>

            <Tabs.Panel value="subs" pt="xs">
              <SubsPanel match={match} onInspect={setSelected} />
            </Tabs.Panel>
          </Tabs>
        </Card>
      </Group>
    </Stack>
  )
}
