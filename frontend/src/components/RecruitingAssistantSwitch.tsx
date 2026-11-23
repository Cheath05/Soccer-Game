import { Switch, Text } from '@mantine/core'

import { useRecruitingAssistant, useSetRecruitingAssistant } from '../api/recruiting'

const GROUP: Record<string, string> = { GK: 'keepers', CB: 'centre-backs', FB: 'full-backs', DM: 'defensive mids', CM: 'central mids', AM: 'attacking mids', W: 'wingers', ST: 'strikers' }

/** The recruiting assistant: each Monday until signing day, targets and offers where next season's
 * squad is short of a balanced roster (22 Nov: not leaver for leaver), pulling its own surplus. */
export default function RecruitingAssistantSwitch() {
  const a = useRecruitingAssistant().data
  const set = useSetRecruitingAssistant()
  if (!a) return null
  const leaving = Object.entries(a.leaving)
  const needs = Object.entries(a.needs ?? {})
  const places = a.places_left ?? null
  const short = needs.reduce((sum, [, n]) => sum + n, 0)
  return (
    <div>
      <Switch
        label="Assistant recruits for next season's squad"
        description="Each Monday from the day offers open until signing day (and now), your assistant compares next season's squad (the players staying and your committed class) with a balanced roster, position by position. Where it's short it makes the best realistic recruits Top targets and offers each the scholarship he hopes for (about one and a half offers a place, since some will say no), the biggest gaps first; where a position is covered it withdraws its own offers still open. It stops when your money or places run out, and leaves your own targets and offers alone."
        checked={a.auto}
        disabled={set.isPending}
        onChange={(e) => set.mutate(e.currentTarget.checked)}
      />
      <Text size="xs" c="dimmed" mt={4}>
        Leaving after this season: {leaving.length ? leaving.map(([g, n]) => `${n} ${GROUP[g] ?? g}`).join(', ') : 'nobody'}.
      </Text>
      <Text size="xs" mt={2}>
        Still needed next season: {needs.length ? needs.map(([g, n]) => `${n} ${GROUP[g] ?? g}`).join(', ') : 'nothing: every position is covered'}.
      </Text>
      {places !== null && short > 0 && places < short && (
        <Text size="xs" c="orange" mt={2}>
          Your roster has {Math.max(0, places)} place{places === 1 ? '' : 's'} left next season for {short} needed: the assistant can’t offer more than your places allow. Pull an offer, or a commitment at a position you have too many of, to make room.
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
