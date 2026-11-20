import { Switch, Text } from '@mantine/core'

import { useSetTrainingSetting, useTrainingSetting } from '../api/hooks'

/** The assistant trains positions: every player not learning one starts on his best alternate
 * position (the one he already plays a little and knows best), now and each month. */
export default function AutoTrainingSwitch({ compact = false }: { compact?: boolean }) {
  const setting = useTrainingSetting().data
  const set = useSetTrainingSetting()
  if (!setting) return null
  return (
    <div>
      <Switch
        size={compact ? 'xs' : 'sm'}
        label="Assistant trains positions"
        description={compact ? undefined : 'Every player not learning a position starts on his best alternate one (a position he already plays a little), now and on the 1st of each month, until he is natural everywhere he plays. You can still choose or stop any player’s training yourself.'}
        checked={setting.auto}
        disabled={set.isPending}
        onChange={(e) => set.mutate(e.currentTarget.checked)}
      />
      {setting.auto && (
        <Text size="xs" c="dimmed" mt={4}>
          {setting.training} of your players are learning a position.
        </Text>
      )}
      {set.error && (
        <Text size="xs" c="red">
          {set.error.message}
        </Text>
      )}
    </div>
  )
}
