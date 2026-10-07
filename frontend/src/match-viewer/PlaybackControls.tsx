import { Button, Group, Paper, SegmentedControl, Switch, Tooltip } from '@mantine/core'

import type { LiveMatch } from './useLiveMatch'

interface Props {
  match: LiveMatch
  showNames: boolean
  onShowNames: (value: boolean) => void
}

// Speed only changes how fast you watch: the match is the same at any speed.
export default function PlaybackControls({ match, showNames, onShowNames }: Props) {
  const { live, ended, send } = match
  const over = !live || !!ended || live.finished
  return (
    <Paper withBorder radius="lg" p="xs">
      <Group gap="sm" wrap="wrap">
        <Button
          w={104}
          radius="xl"
          variant={live?.paused ? 'filled' : 'light'}
          color={live?.paused ? 'teal' : 'gray'}
          disabled={over || live?.atBreak}
          onClick={() => send({ type: live?.paused ? 'resume' : 'pause' })}
        >
          {live?.paused ? 'Play' : 'Pause'}
        </Button>
        <Tooltip label="1× plays each half in about 5 minutes">
          <SegmentedControl
            size="xs"
            radius="xl"
            value={String(live?.speed ?? 1)}
            onChange={(v) => send({ type: 'speed', value: Number(v) })}
            data={(live?.speeds ?? [1]).map((s) => ({ value: String(s), label: `${s}×` }))}
          />
        </Tooltip>
        <SegmentedControl
          size="xs"
          radius="xl"
          value={live?.mode === 'highlights' ? 'highlights' : 'full'}
          onChange={(v) => send({ type: 'mode', value: v })}
          data={[
            { value: 'full', label: 'Full match' },
            { value: 'highlights', label: 'Highlights' },
          ]}
        />
        <Button variant="default" radius="xl" disabled={over} onClick={() => send({ type: 'finish' })}>
          Instant result
        </Button>
        <Switch size="sm" label="Names" checked={showNames} onChange={(e) => onShowNames(e.currentTarget.checked)} />
      </Group>
    </Paper>
  )
}
