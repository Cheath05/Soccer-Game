import { Select } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import { useClubSearch } from '../api/hooks'

/** Finds any club by a few letters of its name (accents ignored) and opens its page, which has
 * the squad and results. The server does the matching (GET /api/clubs/search). */
export default function ClubSearch({ w, onPick }: { w?: number | string; onPick?: () => void }) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const found = useClubSearch(query)
  const results = query.trim().length >= 2 ? (found.data ?? []) : []
  const data = results.map((c) => ({
    value: String(c.id),
    label: c.name,
    detail: [c.competition, c.nation].filter(Boolean).join(' · '),
  }))
  return (
    <Select
      aria-label="Find a club"
      placeholder="Find a club…"
      w={w}
      searchable
      clearable
      value={null}
      searchValue={query}
      onSearchChange={setQuery}
      data={data}
      filter={({ options }) => options}
      nothingFoundMessage={query.trim().length >= 2 && !found.isFetching ? 'No club found' : null}
      renderOption={({ option }) => {
        const d = data.find((x) => x.value === option.value)
        return (
          <div>
            <div>{option.label}</div>
            {d?.detail && <div style={{ fontSize: 'var(--mantine-font-size-xs)', opacity: 0.65 }}>{d.detail}</div>}
          </div>
        )
      }}
      onChange={(id) => {
        if (!id) return
        setQuery('')
        onPick?.()
        void navigate({ to: '/clubs/$clubId', params: { clubId: id } })
      }}
    />
  )
}
