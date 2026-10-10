// Position training for the user's own players. Familiarity runs 0..natural (18).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'

export interface Training {
  position: string | null
  progress: number // 0-1 towards the next point of familiarity
  natural: number
  rate_per_month: number
  positions: { position: string; familiarity: number }[]
}

export const useTraining = (playerId: number, enabled: boolean) =>
  useQuery({
    queryKey: ['training', playerId],
    queryFn: () => api.get<Training>(`/players/${playerId}/training`),
    enabled,
  })

export function useSetTraining(playerId: number) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (position: string | null) => api.put<Training>(`/players/${playerId}/training`, { position }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['training', playerId] })
      void client.invalidateQueries({ queryKey: ['player', playerId] })
    },
  })
}
