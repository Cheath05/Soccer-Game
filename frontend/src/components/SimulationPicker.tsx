import { Accordion, Badge, Button, Checkbox, Group, Loader, Stack, Text } from '@mantine/core'

import { useNations, useSimLeagues } from '../api/hooks'
import type { SimLeague } from '../api/types'
import { BIG_FIVE, groupByNation } from '../lib/format'

/** Which leagues are fully simulated and which get fast results (Settings → Simulation, and the
 * new-career options). `fast` lists the fast ones; `userLeague` is the user's own league, always
 * fully simulated. Presets for the usual choices, then every league by continent and country. */
export default function SimulationPicker({
  fast,
  onChange,
  userLeague,
  disabled,
}: {
  fast: string[]
  onChange: (fast: string[]) => void
  userLeague: string | null
  disabled?: boolean
}) {
  const leagues = useSimLeagues()
  const nations = useNations()
  if (!leagues.data) return leagues.error ? <Text c="red">{leagues.error.message}</Text> : <Loader size="sm" />
  const all = leagues.data
  const fastSet = new Set(fast)
  const full = (l: SimLeague) => l.key === userLeague || !fastSet.has(l.key)
  const homeNation = all.find((l) => l.key === userLeague)?.nation
  const keepOnly = (keep: (l: SimLeague) => boolean) => onChange(all.filter((l) => !keep(l) && l.key !== userLeague).map((l) => l.key))
  const set = (keys: string[], on: boolean) => {
    const next = new Set(fast)
    for (const k of keys) {
      if (on) next.delete(k)
      else if (k !== userLeague) next.add(k)
    }
    onChange([...next].sort())
  }
  const groups = groupByNation(all, nations.data)
  const continents = new Map<string, typeof groups>()
  for (const g of groups) {
    const c = g.continent ?? 'Other'
    continents.set(c, [...(continents.get(c) ?? []), g])
  }
  const fullCount = all.filter(full).length

  return (
    <Stack gap="sm">
      <Text size="sm" c="dimmed">
        Fully simulated leagues play every match minute by minute, with cards, injuries and fitness. The rest get a fast result: the score from the teams’ strengths, with scorers,
        appearances and minutes for every player, but no cards or injuries. Their clubs are still fully simulated in continental competitions and in cup ties against fully simulated clubs.
        Fewer fully simulated leagues make simulating faster.
      </Text>
      <Group gap="xs">
        <Button size="compact-sm" variant="light" disabled={disabled} onClick={() => onChange([])}>
          Everything
        </Button>
        <Button
          size="compact-sm"
          variant="light"
          disabled={disabled}
          onClick={() => keepOnly((l) => (BIG_FIVE.includes(l.nation) && l.tier === 1) || (homeNation !== undefined && l.nation === homeNation))}
        >
          Big five + my country
        </Button>
        <Button size="compact-sm" variant="light" disabled={disabled || !homeNation} onClick={() => keepOnly((l) => l.nation === homeNation)}>
          My country
        </Button>
        <Button size="compact-sm" variant="light" disabled={disabled || !userLeague} onClick={() => keepOnly(() => false)}>
          My league only
        </Button>
      </Group>
      <Text size="sm" fw={600}>
        {fullCount} of {all.length} fully simulated
      </Text>
      <Accordion variant="separated" multiple>
        {[...continents.entries()].map(([continent, countries]) => {
          const ls = countries.flatMap((c) => c.leagues)
          const on = ls.filter(full).length
          return (
            <Accordion.Item key={continent} value={continent}>
              <Accordion.Control>
                <Group justify="space-between" wrap="nowrap" pr="xs">
                  <Text fw={600}>{continent}</Text>
                  <Badge variant="light" color={on === ls.length ? 'teal' : on === 0 ? 'gray' : 'blue'}>
                    {on}/{ls.length} full
                  </Badge>
                </Group>
              </Accordion.Control>
              <Accordion.Panel>
                <Stack gap="sm">
                  <Group gap="xs">
                    <Button size="compact-xs" variant="subtle" disabled={disabled} onClick={() => set(ls.map((l) => l.key), true)}>
                      All full
                    </Button>
                    <Button size="compact-xs" variant="subtle" disabled={disabled} onClick={() => set(ls.map((l) => l.key), false)}>
                      All fast
                    </Button>
                  </Group>
                  {countries.map((country) => {
                    const count = country.leagues.filter(full).length
                    return (
                      <div key={country.code}>
                        <Checkbox
                          label={<Text fw={600} size="sm">{country.name}</Text>}
                          checked={count === country.leagues.length}
                          indeterminate={count > 0 && count < country.leagues.length}
                          disabled={disabled}
                          onChange={(e) => set(country.leagues.map((l) => l.key), e.currentTarget.checked)}
                        />
                        <Stack gap={4} pl={28} mt={4}>
                          {country.leagues.map((l) => (
                            <Checkbox
                              key={l.key}
                              size="xs"
                              label={l.key === userLeague ? `${l.name} (your league: always full)` : l.name}
                              checked={full(l)}
                              disabled={disabled || l.key === userLeague}
                              onChange={(e) => set([l.key], e.currentTarget.checked)}
                            />
                          ))}
                        </Stack>
                      </div>
                    )
                  })}
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>
          )
        })}
      </Accordion>
    </Stack>
  )
}
