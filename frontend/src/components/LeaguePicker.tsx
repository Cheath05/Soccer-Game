import { SegmentedControl, Select } from '@mantine/core'

import { competitionNation, groupByNation } from '../lib/format'

/** Picks a league in two parts: its nation, then one of that nation's leagues in tier order.
 * Choosing another nation jumps to its top league. The controls sit side by side, for the parent
 * Group to lay out. The nation is a Select (a SegmentedControl while there are 3 or fewer, and
 * left out when there is one); the leagues are a SegmentedControl, or on a phone a Select, as
 * four league names do not fit its width. */
export default function LeaguePicker({
  leagues,
  value,
  onChange,
}: {
  leagues: { key: string; name: string; tier: number; nation?: string }[]
  value: string
  onChange: (key: string) => void
}) {
  const nations = groupByNation(leagues)
  const nation = competitionNation(leagues.find((l) => l.key === value) ?? { key: value })
  const nationData = nations.map((n) => ({ value: n.code, label: n.name }))
  const leagueData = (nations.find((n) => n.code === nation)?.leagues ?? []).map((l) => ({ value: l.key, label: l.name.replace('EFL ', '') }))
  const pickNation = (code: string | null) => {
    const top = nations.find((n) => n.code === code)?.leagues[0]
    if (top) onChange(top.key)
  }

  return (
    <>
      {nations.length > 3 && <Select aria-label="Nation" w={140} value={nation} onChange={pickNation} allowDeselect={false} data={nationData} />}
      {nations.length > 1 && nations.length <= 3 && <SegmentedControl aria-label="Nation" value={nation} onChange={pickNation} data={nationData} />}
      <SegmentedControl aria-label="League" visibleFrom="sm" value={value} onChange={onChange} data={leagueData} />
      <Select aria-label="League" hiddenFrom="sm" w={170} value={value} onChange={(key) => key && onChange(key)} allowDeselect={false} data={leagueData} />
    </>
  )
}
