import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, api } from './client'
import type {
  AdvanceResult,
  CalendarData,
  Career,
  ClubHistory,
  Finances,
  ClubOverview,
  ClubPlayer,
  Competition,
  Cup,
  CupSummary,
  Fixture,
  Health,
  LeagueOption,
  MatchReport,
  PlayerDetail,
  PlayerSeason,
  SaveSlot,
  Season,
  SimStatus,
  SquadPlayer,
  Table,
  Tactics,
  TacticsUpdate,
} from './types'

// Refetched on focus once stale, so a tab left open across an update notices the new server.
export const useHealth = () =>
  useQuery({ queryKey: ['health'], queryFn: () => api.get<Health>('/health'), staleTime: 60_000, refetchOnWindowFocus: true })

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

export const useCups = () => useQuery({ queryKey: ['cups'], queryFn: () => api.get<CupSummary[]>('/cups') })

export const useCup = (key: string | undefined, season?: number | null) =>
  useQuery({
    queryKey: ['cup', key, season ?? null],
    queryFn: () => api.get<Cup>(`/cups/${key}${season ? `?season=${season}` : ''}`),
    enabled: !!key,
  })

export const useSeasons = () => useQuery({ queryKey: ['seasons'], queryFn: () => api.get<Season[]>('/seasons') })

export const useClubHistory = (clubId: number | undefined) =>
  useQuery({ queryKey: ['club-history', clubId], queryFn: () => api.get<ClubHistory>(`/clubs/${clubId}/history`), enabled: !!clubId })

export const useSquad = (clubId: number | undefined) =>
  useQuery({ queryKey: ['squad', clubId], queryFn: () => api.get<SquadPlayer[]>(`/clubs/${clubId}/squad`), enabled: !!clubId })

export const useClub = (clubId: number) =>
  useQuery({ queryKey: ['club', clubId], queryFn: () => api.get<ClubOverview>(`/clubs/${clubId}`) })

export const useClubPlayers = (clubId: number) =>
  useQuery({ queryKey: ['club-players', clubId], queryFn: () => api.get<ClubPlayer[]>(`/clubs/${clubId}/players`), enabled: clubId > 0 })

export const useClubFixtures = (clubId: number | undefined, season?: number | null) =>
  useQuery({
    queryKey: ['fixtures', clubId, season ?? null],
    queryFn: () => api.get<Fixture[]>(`/clubs/${clubId}/fixtures${season ? `?season=${season}` : ''}`),
    enabled: !!clubId,
  })

export const usePlayer = (id: number) =>
  useQuery({ queryKey: ['player', id], queryFn: () => api.get<PlayerDetail>(`/players/${id}`) })

export const usePlayerSeasons = (id: number) =>
  useQuery({ queryKey: ['player-seasons', id], queryFn: () => api.get<PlayerSeason[]>(`/players/${id}/seasons`) })

export const useMatch = (id: number) =>
  useQuery({ queryKey: ['match', id], queryFn: () => api.get<MatchReport>(`/fixtures/${id}`) })

export const useFinances = (enabled = true) =>
  useQuery({ queryKey: ['finances'], queryFn: () => api.get<Finances>('/finances'), enabled })

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

/** The user's calendar between two ISO dates. */
export const useCalendar = (from: string, to: string) =>
  useQuery({
    queryKey: ['calendar', from, to],
    queryFn: () => api.get<CalendarData>(`/calendar?from=${from}&to=${to}`),
    placeholderData: (previous) => previous,
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

/** `budget` is the sandbox: euros for fees and wages to start with (null: the board's own).
 * `boardEnabled` false plays without a board. */
export function useNewCareer() {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: (args: { slot: number; clubId: number; manager: string; budget?: number | null; boardEnabled?: boolean }) =>
      api.post<Career>(`/saves/${args.slot}/new`, {
        club_id: args.clubId,
        manager_name: args.manager,
        budget_eur: args.budget ?? null,
        board_enabled: args.boardEnabled ?? true,
      }),
    onSuccess: invalidate,
  })
}

/** Turn the user's board on or off: the budget is worked out again, so the finances (and the
 * club's overview, which shows the budget) are refetched. The answer is the new finances: the
 * page shows them at once, and the refetch only confirms them. */
export function useSetBoard() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (enabled: boolean) => api.put<Finances>('/career/board', { enabled }),
    onSuccess: (data) => {
      client.setQueryData(['finances'], data)
      void client.invalidateQueries({ queryKey: ['finances'] })
      void client.invalidateQueries({ queryKey: ['club'] })
    },
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

export function useReleasePlayer() {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: (playerId: number) => api.post<PlayerDetail>(`/players/${playerId}/release`),
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
