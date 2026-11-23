import { Switch, Text } from '@mantine/core'

import { useSetTrainingSetting, useTrainingSetting } from '../api/hooks'

/** The assistant trains positions: every player not learning one starts on his best alternate
 * position (the one he already plays a little and knows best), now and each month. A switch for
 * each of the user's jobs: his club's players, and his national team's squad. */
export default function AutoTrainingSwitch({ compact = false, team = 'club' }: { compact?: boolean; team?: 'club' | 'nation' }) {
  const setting = useTrainingSetting().data
  const set = useSetTrainingSetting()
  if (!setting) return null
  const nation = team === 'nation'
  if (nation ? setting.nation_auto === null : !setting.has_club) return null
  const on = nation ? !!setting.nation_auto : setting.auto
  const count = nation ? (setting.nation_training ?? 0) : setting.training
  return (
    <div>
      <Switch
        size={compact ? 'xs' : 'sm'}
        label={nation ? 'Assistant trains your national team’s positions' : 'Assistant trains your club’s positions'}
        description={
          compact
            ? undefined
            : nation
              ? 'Every player in your national team’s squad who isn’t learning a position starts on his best alternate one (a position he already plays a little), now and on the 1st of each month. He learns it at his club. You can still choose or stop any player’s training yourself.'
              : 'Every player not learning a position starts on his best alternate one (a position he already plays a little), now and on the 1st of each month, until he is natural everywhere he plays. You can still choose or stop any player’s training yourself.'
        }
        checked={on}
        disabled={set.isPending}
        onChange={(e) => set.mutate(nation ? { nation_auto: e.currentTarget.checked } : { auto: e.currentTarget.checked })}
      />
      {on && (
        <Text size="xs" c="dimmed" mt={4}>
          {count} {nation ? 'of your squad’s players are' : 'of your players are'} learning a position.
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
