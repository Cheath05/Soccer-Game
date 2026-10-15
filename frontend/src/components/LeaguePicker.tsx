import { Group, SegmentedControl, Select, Stack } from '@mantine/core'

import { useNations } from '../api/hooks'
import { competitionNation, groupByNation } from '../lib/format'
import NationPicker from './NationPicker'

/** Picks a league in two parts, as two rows: its country, then one of that country's leagues in
 * tier order. Choosing another country jumps to its top league. The country is a NationPicker
 * (buttons for `home`, the user's own country, and the big five, a search box for the rest and a
 * continent filter, in the server's ranking order); the leagues are a SegmentedControl, or on a
 * phone a Select, as four league names do not fit its width. A block for the page to place. */
export default function LeaguePicker({
  leagues,
  value,
  onChange,
  home,
}: {
  leagues: { key: string; name: string; tier: number; nation?: string }[]
  value: string
  onChange: (key: string) => void
  home?: string
}) {
  const nations = groupByNation(leagues, useNations().data)
  const nation = competitionNation(leagues.find((l) => l.key === value) ?? { key: value })
  const leagueData = (nations.find((n) => n.code === nation)?.leagues ?? []).map((l) => ({ value: l.key, label: l.name.replace('EFL ', '') }))
  const pickNation = (code: string) => {
    const top = nations.find((n) => n.code === code)?.leagues[0]
    if (top) onChange(top.key)
  }

  return (
    <Stack gap="xs">
      <NationPicker nations={nations} value={nation} onChange={pickNation} home={home} />
      <Group>
        <SegmentedControl aria-label="League" visibleFrom="sm" value={value} onChange={onChange} data={leagueData} />
        <Select aria-label="League" hiddenFrom="sm" w="100%" value={value} onChange={(key) => key && onChange(key)} allowDeselect={false} data={leagueData} />
      </Group>
    </Stack>
  )
}
