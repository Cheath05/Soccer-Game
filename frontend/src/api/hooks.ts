import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, api } from './client'
import type {
  AdvanceResult,
  Career,
  ClubHistory,
  ClubOverview,
  ClubPlayer,
  Competition,
  Fixture,
  LeagueOption,
  MatchReport,
  PlayerDetail,
  SaveSlot,
  Season,
  SimStatus,
  SquadPlayer,
  Table,
  Tactics,
  TacticsUpdate,
} from './types'

export const useCareer = () =>
  useQuery({
    queryKey: ['career'],
    queryFn: () => api.get<Career>('/career'),
    retry: (count, error) => !(error instanceof ApiError && error.status === 409) && count < 2,
  })

export const useSaves = () => useQuery({ queryKey: ['saves'], queryFn: () => api.get<SaveSlot[]>('/saves') })

export const useWorldLeagues = () =>
  useQuery({ queryKey: ['world-leagues'], queryFn: () => api.get<LeagueOption[]>('/world/leagues'), staleTime: Infinity })

export const useCompetitions = () =>
  useQuery({ queryKey: ['competitions'], queryFn: () => api.get<Competition[]>('/competitions') })

export const useTable = (key: string | undefined, season?: number | null) =>
  useQuery({
    queryKey: ['table', key, season ?? null],
    queryFn: () => api.get<Table>(`/competitions/${key}/table${season ? `?season=${season}` : ''}`),
    enabled: !!key,
  })

export const useSeasons = () => useQuery({ queryKey: ['seasons'], queryFn: () => api.get<Season[]>('/seasons') })

export const useClubHistory = (clubId: number) =>
  useQuery({ queryKey: ['club-history', clubId], queryFn: () => api.get<ClubHistory>(`/clubs/${clubId}/history`) })

export const useSquad = (clubId: number | undefined) =>
  useQuery({ queryKey: ['squad', clubId], queryFn: () => api.get<SquadPlayer[]>(`/clubs/${clubId}/squad`), enabled: !!clubId })

export const useClub = (clubId: number) =>
  useQuery({ queryKey: ['club', clubId], queryFn: () => api.get<ClubOverview>(`/clubs/${clubId}`) })

export const useClubPlayers = (clubId: number) =>
  useQuery({ queryKey: ['club-players', clubId], queryFn: () => api.get<ClubPlayer[]>(`/clubs/${clubId}/players`) })

export const useClubFixtures = (clubId: number | undefined) =>
  useQuery({ queryKey: ['fixtures', clubId], queryFn: () => api.get<Fixture[]>(`/clubs/${clubId}/fixtures`), enabled: !!clubId })

export const usePlayer = (id: number) =>
  useQuery({ queryKey: ['player', id], queryFn: () => api.get<PlayerDetail>(`/players/${id}`) })

export const useMatch = (id: number) =>
  useQuery({ queryKey: ['match', id], queryFn: () => api.get<MatchReport>(`/fixtures/${id}`) })

export const useTactics = () => useQuery({ queryKey: ['tactics'], queryFn: () => api.get<Tactics>('/tactics') })

/** Anything that moves the game on invalidates every cached view of it. */
function useInvalidateAll() {
  const client = useQueryClient()
  return () => client.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'world-leagues' })
}

export function useAdvance() {
  const invalidate = useInvalidateAll()
  return useMutation({ mutationFn: () => api.post<AdvanceResult>('/career/advance'), onSuccess: invalidate })
}

/** The latest sim-to-date job, polled twice a second while it runs. */
export const useSimStatus = () =>
  useQuery({
    queryKey: ['sim'],
    queryFn: () => api.get<SimStatus | null>('/career/sim'),
    refetchInterval: (query) => (query.state.data?.running ? 500 : false),
  })

export function useStartSim() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (until: string) => api.post<SimStatus>('/career/sim', { until }),
    onSuccess: (data) => client.setQueryData(['sim'], data),
  })
}

export function useStopSim() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<SimStatus | null>('/career/sim/stop'),
    onSuccess: (data) => client.setQueryData(['sim'], data),
  })
}

export function usePlayInstant() {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: (fixtureId: number) => api.post<MatchReport>(`/fixtures/${fixtureId}/play`),
    onSuccess: invalidate,
  })
}

export function useSaveTactics() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: TacticsUpdate) => api.put<Tactics>('/tactics', body),
    onSuccess: (data) => client.setQueryData(['tactics'], data),
  })
}

export function useNewCareer() {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: (args: { slot: number; clubId: number; manager: string }) =>
      api.post<Career>(`/saves/${args.slot}/new`, { club_id: args.clubId, manager_name: args.manager }),
    onSuccess: invalidate,
  })
}

export function useLoadCareer() {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: (args: { slot: number; autosave?: boolean }) =>
      api.post<Career>(`/saves/${args.slot}/load${args.autosave ? '?autosave=true' : ''}`),
    onSuccess: invalidate,
  })
}

export function useSaveGame() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<SaveSlot[]>('/saves/save'),
    onSuccess: (data) => client.setQueryData(['saves'], data),
  })
}
