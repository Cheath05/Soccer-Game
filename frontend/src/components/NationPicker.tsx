import { Box, Chip, Group, SegmentedControl, Select, Text } from '@mantine/core'
import type { ComboboxParsedItem, OptionsFilter } from '@mantine/core'
import { useState } from 'react'
import type { ReactNode } from 'react'

import { useDevice } from '../lib/device'
import { BIG_FIVE, bigFiveIndex, matchesSearch, nationSearchText } from '../lib/format'

/** A country to pick. `leagues` are the competitions it has: they are listed under its name in
 * the search, and searched too ("Eliteserien" finds Norway). `continent` is the server's. */
export interface NationOption {
  code: string
  name: string
  continent?: string
  featured?: boolean
  leagues?: { name?: string }[]
}

/** A row that scrolls sideways inside itself when it is wider than the page (on a phone). Its
 * padding is given back as negative margin: it only leaves room for a focus ring, which the
 * scrolling would otherwise cut off. */
function ScrollRow({ children }: { children: ReactNode }) {
  return (
    <Box maw="calc(100% + 8px)" style={{ overflowX: 'auto', scrollbarWidth: 'thin', padding: 4, margin: -4 }}>
      {children}
    </Box>
  )
}

/** Picks a country (by its code) without a long list in the way.
 * - Always visible: buttons for the user's own country (`home`) and the big five.
 * - "All countries": a search box over every country, grouped by continent in ranking order. It
 *   finds a country by its name or by the name of one of its leagues or cups, accents ignored.
 * - A continent filter that narrows that search, only where the countries span several continents.
 * A few countries (4 or fewer) are all buttons; one country needs no picker. It is a row that wraps,
 * for a parent to lay out; the League and Cups pages and the season summary use it. */
export default function NationPicker({
  nations,
  value,
  onChange,
  home,
}: {
  nations: NationOption[]
  value: string
  onChange: (code: string) => void
  home?: string
}) {
  const { phone } = useDevice()
  const [continent, setContinent] = useState('all')
  const [searching, setSearching] = useState(false)
  if (nations.length < 2) return null

  const byCode = new Map(nations.map((n) => [n.code, n]))
  const featured = nations
    .filter((n) => n.featured ?? BIG_FIVE.includes(n.code))
    .map((n) => n.code)
    .sort((a, b) => bigFiveIndex(a) - bigFiveIndex(b))
  const quickCodes =
    nations.length <= 4 ? nations.map((n) => n.code) : [...new Set([...(home ? [home] : []), ...featured])].filter((code) => byCode.has(code))
  const inQuick = quickCodes.includes(value)
  const hasMore = nations.some((n) => !quickCodes.includes(n.code))
  const continents = [...new Set(nations.map((n) => n.continent).filter((c): c is string => !!c))]
  const shown = continents.includes(continent) ? continent : 'all'

  // What the search lists and matches: the country, its other names and its leagues' names.
  const matchText = new Map<string, string>()
  const detail = new Map<string, string>()
  for (const n of nations) {
    const names = (n.leagues ?? []).map((l) => l.name).filter((name): name is string => !!name)
    matchText.set(n.code, `${nationSearchText(n.code, n.name)} ${names.join(' ')}`)
    detail.set(n.code, names.join(' · '))
  }
  const groups = new Map<string, { value: string; label: string }[]>()
  for (const n of nations) {
    if (shown !== 'all' && n.continent !== shown) continue
    const label = n.continent ?? 'Other'
    const items = groups.get(label) ?? []
    items.push({ value: n.code, label: n.name })
    groups.set(label, items)
  }
  const data = continents.length > 1 ? [...groups].map(([group, items]) => ({ group, items })) : [...groups.values()].flat()
  const filter: OptionsFilter = ({ options, search }) => {
    const keep = (option: { value: string; label: string }) => matchesSearch(matchText.get(option.value) ?? option.label, search)
    const found: ComboboxParsedItem[] = []
    for (const item of options) {
      if ('group' in item) {
        const items = item.items.filter(keep)
        if (items.length > 0) found.push({ group: item.group, items })
      } else if (keep(item)) found.push(item)
    }
    return found
  }

  return (
    // `contain: inline-size`: this block's own width never counts towards the size of what holds it.
    // A dialog's scroll area shrinks to fit its widest content, and a row of buttons that scrolls
    // would otherwise stretch the dialog beyond a phone's width.
    <Box style={{ contain: 'inline-size' }}>
      <Group gap="xs" wrap="wrap">
        {quickCodes.length > 0 && (
          <ScrollRow>
            <Chip.Group value={inQuick ? value : ''} onChange={(code) => typeof code === 'string' && code && onChange(code)}>
              <Group gap={6} wrap="nowrap" role="radiogroup" aria-label="Country">
                {quickCodes.map((code) => (
                  <Chip key={code} value={code} size={phone ? 'md' : 'sm'} variant="light">
                    {byCode.get(code)?.name ?? code}
                  </Chip>
                ))}
              </Group>
            </Chip.Group>
          </ScrollRow>
        )}
        {hasMore && (
          <Select
            aria-label="All countries"
            placeholder={searching ? 'Country or league name' : 'All countries'}
            w={{ base: '100%', sm: 230 }}
            searchable
            selectFirstOptionOnChange
            allowDeselect={false}
            maxDropdownHeight={320}
            value={inQuick || !value ? null : value}
            onChange={(code) => code && onChange(code)}
            data={data}
            filter={filter}
            nothingFoundMessage="No country or league found"
            onDropdownOpen={() => setSearching(true)}
            onDropdownClose={() => setSearching(false)}
            // The box carries the selection when the country isn't one of the buttons.
            styles={!inQuick && value ? { input: { borderColor: 'var(--mantine-primary-color-filled)' } } : undefined}
            renderOption={({ option }) => (
              <Box miw={0} w="100%">
                <Text size="sm" truncate>
                  {option.label}
                </Text>
                {detail.get(option.value) && (
                  // Not `c="dimmed"`: the option the keyboard is on has a filled background.
                  <Text size="xs" truncate style={{ opacity: 0.65 }}>
                    {detail.get(option.value)}
                  </Text>
                )}
              </Box>
            )}
          />
        )}
        {hasMore && continents.length > 1 && (
          <ScrollRow>
            <SegmentedControl
              size="xs"
              aria-label="Continent"
              value={shown}
              onChange={setContinent}
              data={[{ value: 'all', label: 'All' }, ...continents.map((c) => ({ value: c, label: c }))]}
            />
          </ScrollRow>
        )}
      </Group>
    </Box>
  )
}
