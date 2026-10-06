import { SegmentedControl, Select } from '@mantine/core'

/** Picks a nation (by its code): a Select once there are more than 3 (a phone-width list of
 * country names does not fit a SegmentedControl), a SegmentedControl for 2 or 3, and nothing for
 * one. For the parent Group to lay out beside its other controls; the League and Cups pages use it. */
export default function NationPicker({
  nations,
  value,
  onChange,
}: {
  nations: { code: string; name: string }[]
  value: string
  onChange: (code: string) => void
}) {
  const data = nations.map((n) => ({ value: n.code, label: n.name }))
  const pick = (code: string | null) => code && onChange(code)
  if (nations.length > 3) return <Select aria-label="Nation" w={140} value={value} onChange={pick} allowDeselect={false} data={data} />
  if (nations.length > 1) return <SegmentedControl aria-label="Nation" value={value} onChange={pick} data={data} />
  return null
}
