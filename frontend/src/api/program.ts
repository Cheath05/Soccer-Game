// The NCAA program builder mode for a college coach (W9d; backend api/program.py).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'

export interface ProgramFacility {
  kind: 'training' | 'stadium'
  level: number
  effect: string
  next_effect: string | null
  next_cost_eur: number | null // null at the top level
  upkeep_eur: number
  building_to: number | null
  ready_season: string | null
}

export interface Program {
  mode: 'classic' | 'builder'
  balance_eur: number
  season: { kind: string; amount_eur: number }[]
  class_budget: number // full scholarships for next season's class
  class_committed: number
  class_affordable: number
  scholarship_eur: number
  next_allocation_eur: number
  build_cutoff: string
  facilities: ProgramFacility[]
  capacity: number
  crowds: { fixture_id: number; date: string; opponent: string; attendance: number }[]
}

export const useProgram = (enabled = true) => useQuery({ queryKey: ['program'], queryFn: () => api.get<Program>('/program'), enabled })

function useProgramAction<T>(fn: (arg: T) => Promise<Program>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (data) => {
      client.setQueryData(['program'], data)
      void client.invalidateQueries({ queryKey: ['recruiting'] })
      void client.invalidateQueries({ queryKey: ['career'] })
    },
  })
}

export const useSetClassBudget = () => useProgramAction((budget: number) => api.put<Program>('/program/class-budget', { budget }))
export const useUpgrade = () => useProgramAction((kind: string) => api.post<Program>(`/program/upgrade/${kind}`))
export const useTurnOnBuilder = () => useProgramAction(() => api.put<Program>('/settings/college-mode', { mode: 'builder' }))
