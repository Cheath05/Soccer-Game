import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'
import type { ClubRef } from './types'

// GET /api/club/hall-of-fame (api/hall_of_fame.py): everyone who has played for your club in the
// career, and its Hall of fame.

export interface FormerPlayer {
  player_id: number
  name: string
  position: string
  age: number
  first_season: string
  last_season: string
  seasons: number
  appearances: number
  starts: number
  minutes: number
  goals: number
  assists: number
  average_rating: number | null
  yellow: number
  red: number
  titles: string[]
  now: 'with_you' | 'club' | 'free_agent' | 'retired'
  club: ClubRef | null
  hall_of_fame: boolean
  favorite: boolean
}

export interface HallOfFame {
  club: ClubRef
  rule: string
  players: FormerPlayer[]
  favorites: number[]
}

export const useHallOfFame = () => useQuery({ queryKey: ['hall-of-fame'], queryFn: () => api.get<HallOfFame>('/club/hall-of-fame') })

// PUT /api/club/hall-of-fame/favorites/{id}: star or unstar a player.
export function useSetFavorite() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, favorite }: { id: number; favorite: boolean }) => api.put<HallOfFame>(`/club/hall-of-fame/favorites/${id}`, { favorite }),
    onSuccess: (data) => client.setQueryData(['hall-of-fame'], data),
  })
}
