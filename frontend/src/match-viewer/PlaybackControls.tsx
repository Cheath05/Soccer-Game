import { Button, Group, Paper, SegmentedControl, Switch, Tooltip } from '@mantine/core'

import { useDevice } from '../lib/device'
import type { LiveMatch } from './useLiveMatch'

interface Props {
  match: LiveMatch
  showNames: boolean
  onShowNames: (value: boolean) => void
}

// Speed only changes how fast you watch: the match is the same at any speed.
export default function PlaybackControls({ match, showNames, onShowNames }: Props) {
  const { live, ended, send } = match
  const { phone, touch } = useDevice()
  const big = touch || phone // tap targets of at least 44px
  const h = big ? 44 : undefined
  const over = !live || !!ended || live.finished
  return (
    <Paper withBorder radius="lg" p="xs">
      <Group gap={phone ? 'xs' : 'sm'} wrap="wrap">
        <Button
          w={phone ? 96 : 104}
          h={h}
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
            size={big ? 'sm' : 'xs'}
            radius="xl"
            styles={big ? { root: { minHeight: 44 }, label: { minHeight: 36, display: 'flex', alignItems: 'center' } } : undefined}
            value={String(live?.speed ?? 1)}
            onChange={(v) => send({ type: 'speed', value: Number(v) })}
            data={(live?.speeds ?? [1]).map((s) => ({ value: String(s), label: `${s}×` }))}
          />
        </Tooltip>
        <SegmentedControl
          size={big ? 'sm' : 'xs'}
          radius="xl"
          styles={big ? { root: { minHeight: 44 }, label: { minHeight: 36, display: 'flex', alignItems: 'center' } } : undefined}
          value={live?.mode === 'highlights' ? 'highlights' : 'full'}
          onChange={(v) => send({ type: 'mode', value: v })}
          data={[
            { value: 'full', label: 'Full match' },
            { value: 'highlights', label: 'Highlights' },
          ]}
        />
        <Button variant="default" radius="xl" h={h} disabled={over} onClick={() => send({ type: 'finish' })}>
          Instant result
        </Button>
        <Switch size={big ? 'md' : 'sm'} style={big ? { minHeight: 44, display: 'flex', alignItems: 'center' } : undefined} label="Names" checked={showNames} onChange={(e) => onShowNames(e.currentTarget.checked)} />
      </Group>
    </Paper>
  )
}
