import { useNavigate, useSearch } from '@tanstack/react-router'
import { useCallback } from 'react'

/** State kept in the URL's search params, so Back (and a reload) bring the same filters, tab or sort. Changing it replaces
 * the history entry instead of adding one, so Back leaves the page rather than stepping through every tweak. */
export function useUrlState<T>(key: string, fallback: T): [T, (value: T | ((current: T) => T)) => void] {
  const search = useSearch({ strict: false }) as Record<string, unknown>
  const navigate = useNavigate()
  const value = (search[key] === undefined ? fallback : search[key]) as T
  const set = useCallback(
    (next: T | ((current: T) => T)) => {
      void navigate({
        replace: true,
        search: ((prev: Record<string, unknown>) => {
          const current = (prev[key] === undefined ? fallback : prev[key]) as T
          const resolved = typeof next === 'function' ? (next as (c: T) => T)(current) : next
          return { ...prev, [key]: resolved === undefined || resolved === null || resolved === fallback ? undefined : resolved }
        }) as never,
      })
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [navigate, key],
  )
  return [value, set]
}
