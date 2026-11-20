import { Switch, Text } from '@mantine/core'

import { useRecruitingAssistant, useSetRecruitingAssistant } from '../api/recruiting'

const GROUP: Record<string, string> = { GK: 'keepers', CB: 'centre-backs', FB: 'full-backs', DM: 'defensive mids', CM: 'central mids', AM: 'attacking mids', W: 'wingers', ST: 'strikers' }

/** The recruiting assistant: each Monday until signing day, targets and offers for the recruits
 * who'd replace your leavers. */
export default function RecruitingAssistantSwitch() {
  const a = useRecruitingAssistant().data
  const set = useSetRecruitingAssistant()
  if (!a) return null
  const leaving = Object.entries(a.leaving)
  return (
    <div>
      <Switch
        label="Assistant recruits your leavers' replacements"
        description="Each Monday from the day offers open until signing day (and now), your assistant makes the best realistic recruits at each position you're losing Top targets, and offers each the scholarship he hopes for: about twice as many offers as leavers, since some will say no. It stops when your money or places run out, and leaves your own targets and offers alone."
        checked={a.auto}
        disabled={set.isPending}
        onChange={(e) => set.mutate(e.currentTarget.checked)}
      />
      <Text size="xs" c="dimmed" mt={4}>
        Leaving after this season: {leaving.length ? leaving.map(([g, n]) => `${n} ${GROUP[g] ?? g}`).join(', ') : 'nobody'}.
      </Text>
      {set.error && (
        <Text size="xs" c="red">
          {set.error.message}
        </Text>
      )}
    </div>
  )
}
