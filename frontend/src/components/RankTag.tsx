import { useQuery } from '@tanstack/react-query'
import { Text } from '@mantine/core'

import { api } from '../api/client'

// The college top 25 by RPI (GET /api/college/top25): "#12" beside a ranked program's name, so a
// college coach can see a strong opponent at a glance. Nothing for anyone outside it.

export const useTop25 = () =>
  useQuery({
    queryKey: ['college', 'top25'],
    queryFn: () => api.get<{ club_id: number; rank: number }[]>('/college/top25'),
    staleTime: 60_000,
    select: (rows) => new Map(rows.map((r) => [r.club_id, r.rank])),
  })

export function useRank(clubId: number | undefined): number | undefined {
  const top = useTop25().data
  return clubId === undefined ? undefined : top?.get(clubId)
}

/** "#12 " before a top-25 program's name (nothing otherwise). */
export default function RankTag({ clubId }: { clubId: number }) {
  const rank = useRank(clubId)
  if (!rank) return null
  return (
    <Text span c="dimmed" fw={700} fz="0.85em" mr={4} title={`No. ${rank} in the RPI`}>
      #{rank}
    </Text>
  )
}
