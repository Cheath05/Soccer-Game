import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { type Currency, setCurrency, shownCurrency } from '../lib/format'
import { ApiError, api } from './client'
import type {
  AdvanceResult,
  CalendarData,
  Career,
  Changelog,
  ClubHistory,
  ClubOverview,
  ClubPlayer,
  ClubSearchResult,
  ClubWorldCupView,
  CollegeConferenceOption,
  Competition,
  Cup,
  CupSummary,
  Draft,
  Europe,
  EuropeList,
  EuropeRankings,
  Finances,
  Fixture,
  Health,
  InternationalOverview,
  LeagueOption,
  LeaguePlayoff,
  MatchReport,
  MyNation,
  Nation,
  OfferRules,
  PlayerDetail,
  PlayerSeason,
  Qualifiers,
  SaveSlot,
  Season,
  SimLeague,
  SimStatus,
  SimTarget,
  SimulationSettings,
  SquadPlayer,
  Table,
  Tactics,
  TacticsTeam,
  TacticsUpdate,
  WorldCupFinals,
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

/** Show money in another currency: kept with the career, whose prices are then quoted as round
 * figures in it, so everything is fetched again. */
export function useChooseCurrency() {
  const invalidate = useInvalidateAll()
  const hasCareer = useCareer().data !== undefined
  return (next: Currency) => {
    setCurrency(next)
    if (hasCareer) void api.put<Career>('/career/currency', { currency: next }).then(invalidate, () => undefined)
  }
}

export const useSaves = () => useQuery({ queryKey: ['saves'], queryFn: () => api.get<SaveSlot[]>('/saves') })

/** The NCAA programs a new career can coach (W9c), by conference (no career needed). */
export const useCollegePrograms = () =>
  useQuery({ queryKey: ['college-programs'], queryFn: () => api.get<CollegeConferenceOption[]>('/world/college-programs'), staleTime: Infinity })

export const useWorldLeagues = () =>
  useQuery({ queryKey: ['world-leagues'], queryFn: () => api.get<LeagueOption[]>('/world/leagues'), staleTime: Infinity })

/** The countries with a league or a cup, with their continent and their place in the lists. The
 * order follows the career's UEFA ranking, so it is fetched again whenever the game moves on. */
/** Every league that can be given fast results instead of full simulation (no career needed). */
export const useSimLeagues = () =>
  useQuery({ queryKey: ['sim-leagues'], queryFn: () => api.get<SimLeague[]>('/world/simulation'), staleTime: Infinity })

/** The career's Settings → Simulation: which leagues get fast results. */
export const useSimulation = () =>
  useQuery({ queryKey: ['simulation'], queryFn: () => api.get<SimulationSettings>('/settings/simulation') })

export function useSetSimulation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (fast: string[]) => api.put<SimulationSettings>('/settings/simulation', { fast }),
    onSuccess: (data) => client.setQueryData(['simulation'], data),
  })
}

/** Settings → Position training: the assistant trains every player's alternate positions. */
export interface TrainingSetting {
  auto: boolean
  training: number // your players learning a position now
}

export const useTrainingSetting = () => useQuery({ queryKey: ['training-setting'], queryFn: () => api.get<TrainingSetting>('/settings/training') })

export function useSetTrainingSetting() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (auto: boolean) => api.put<TrainingSetting>('/settings/training', { auto }),
    onSuccess: (data) => {
      client.setQueryData(['training-setting'], data)
      void client.invalidateQueries({ queryKey: ['training'] })
    },
  })
}

/** Settings → Transfer offers: whether bids for your players stop the game, wait, or are answered by your prices. */
export const useOfferRules = () => useQuery({ queryKey: ['offer-rules'], queryFn: () => api.get<OfferRules>('/settings/offers') })

export function useSetOfferRules() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { mode: string; value_pct: number | null; loans: string }) => api.put<OfferRules>('/settings/offers', body),
    onSuccess: (data) => client.setQueryData(['offer-rules'], data),
  })
}

/** Your asking price for one of your players, in EUR (null: none). */
export function useSetAskingPrice() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (args: { playerId: number; feeEur: number | null }) => api.put<OfferRules>(`/settings/asking-price/${args.playerId}`, { fee_eur: args.feeEur }),
    onSuccess: (data) => client.setQueryData(['offer-rules'], data),
  })
}

/** International football: the national teams by Elo and the latest results. */
export const useInternational = () =>
  useQuery({ queryKey: ['international'], queryFn: () => api.get<InternationalOverview>('/international') })

/** The World Cup qualifiers: every stage's groups and ties, and who is through. */
export const useQualifiers = () =>
  useQuery({ queryKey: ['wc-qualifiers'], queryFn: () => api.get<Qualifiers>('/international/qualifiers') })

/** The next (or current) FIFA Club World Cup. */
export const useClubWorldCup = () =>
  useQuery({ queryKey: ['club-world-cup'], queryFn: () => api.get<ClubWorldCupView>('/international/club-world-cup') })

/** The World Cup finals: groups and knockout rounds once drawn. */
export const useWorldCupFinals = () =>
  useQuery({ queryKey: ['wc-finals'], queryFn: () => api.get<WorldCupFinals>('/international/world-cup') })

export const useNations = () =>
  useQuery({ queryKey: ['nations'], queryFn: () => api.get<Nation[]>('/world/nations'), staleTime: Infinity, retry: 1 })

export const useCompetitions = () =>
  useQuery({ queryKey: ['competitions'], queryFn: () => api.get<Competition[]>('/competitions') })

export const useTable = (key: string | undefined, season?: number | null, phase?: string | null) =>
  useQuery({
    queryKey: ['table', key, season ?? null, phase ?? null],
    queryFn: () => {
      const query = new URLSearchParams()
      if (season) query.set('season', String(season))
      if (phase) query.set('phase', phase)
      const qs = query.toString()
      return api.get<Table>(`/competitions/${key}/table${qs ? `?${qs}` : ''}`)
    },
    enabled: !!key,
  })

export const usePlayoffs = (key: string | undefined, season?: number | null) =>
  useQuery({
    queryKey: ['playoffs', key, season ?? null],
    queryFn: () => api.get<LeaguePlayoff[]>(`/competitions/${key}/playoffs${season ? `?season=${season}` : ''}`),
    enabled: !!key,
  })

export const useCups = () => useQuery({ queryKey: ['cups'], queryFn: () => api.get<CupSummary[]>('/cups') })

export const useCup = (key: string | undefined, season?: number | null) =>
  useQuery({
    queryKey: ['cup', key, season ?? null],
    queryFn: () => api.get<Cup>(`/cups/${key}${season ? `?season=${season}` : ''}`),
    enabled: !!key,
  })

/** Whether this game has the European competitions, and what is on this season. Only asked once
 * there is a career; a server that predates them answers 404, which reads as "no Europe". */
export const useEuropeList = (enabled = true) =>
  useQuery({ queryKey: ['europe'], queryFn: () => api.get<EuropeList>('/europe'), enabled, retry: false })

export const useEurope = (key: string | undefined, season?: number | null) =>
  useQuery({
    queryKey: ['europe', key, season ?? null],
    queryFn: () => api.get<Europe>(`/europe/${key}${season ? `?season=${season}` : ''}`),
    enabled: !!key,
  })

/** UEFA's country ranking (five seasons) and the club coefficient ranking. */
export const useEuropeRankings = (enabled = true) =>
  useQuery({ queryKey: ['europe', 'rankings'], queryFn: () => api.get<EuropeRankings>('/europe/rankings'), enabled })

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

/** `team` 'nation': the national team the user manages (W8 I5); else his club. */
export const useTactics = (team: TacticsTeam = 'club') =>
  useQuery({ queryKey: ['tactics', team], queryFn: () => api.get<Tactics>(team === 'nation' ? '/tactics?team=nation' : '/tactics') })

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

/** The "Sim to…" choices that depend on the fixture list (the next cup match...), refetched when the game moves on. */
export const useSimTargets = (date: string) =>
  useQuery({ queryKey: ['sim-targets', date], queryFn: () => api.get<SimTarget[]>('/career/sim/targets') })

/** Clubs matching a few letters of a name, for the header search. */
export const useClubSearch = (q: string) =>
  useQuery({
    queryKey: ['club-search', q],
    queryFn: () => api.get<ClubSearchResult[]>(`/clubs/search?q=${encodeURIComponent(q)}`),
    enabled: q.trim().length >= 2,
    placeholderData: (previous) => previous,
    staleTime: 30_000,
  })

/** Sim to a date (ISO), or to a server-computed target (a key from `useSimTargets`). */
export function useStartSim() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (to: string | { target: string }) => api.post<SimStatus>('/career/sim', typeof to === 'string' ? { until: to } : to),
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

export function useSaveTactics(team: TacticsTeam = 'club') {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: TacticsUpdate) => api.put<Tactics>(team === 'nation' ? '/tactics?team=nation' : '/tactics', body),
    onSuccess: (data) => client.setQueryData(['tactics', team], data),
  })
}

/** The national team the user manages (W8 I5): the players he can call up and its matches. */
export const useMyNation = () => useQuery({ queryKey: ['my-nation'], queryFn: () => api.get<MyNation>('/international/my-team') })

export function useNationJob() {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: (code: string | null) => (code ? api.post<MyNation>('/international/job', { code }) : api.delete<MyNation>('/international/job')),
    onSuccess: invalidate,
  })
}

export function useSaveNationSquad() {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: (playerIds: number[]) => api.put<MyNation>('/international/my-team/squad', { player_ids: playerIds }),
    onSuccess: invalidate,
  })
}

/** "Pick best XI and bench": the automatic line-up, each player in the role he rates highest in. */
export function usePickBestXi(team: TacticsTeam = 'club') {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<Tactics>(team === 'nation' ? '/tactics/best?team=nation' : '/tactics/best', {}),
    onSuccess: (data) => client.setQueryData(['tactics', team], data),
  })
}

/** `budget` is the sandbox: euros for fees and wages to start with (null: the board's own).
 * `boardEnabled` false plays without a board. */
export function useNewCareer() {
  const invalidate = useInvalidateAll()
  return useMutation({
    mutationFn: (args: { slot: number; clubId: number | null; collegeProgram?: string | null; collegeMode?: 'classic' | 'builder'; manager: string; budget?: number | null; boardEnabled?: boolean; fastLeagues?: string[] }) =>
      api.post<Career>(`/saves/${args.slot}/new`, {
        club_id: args.clubId,
        college_program: args.collegeProgram ?? null,
        college_mode: args.collegeMode ?? 'classic',
        manager_name: args.manager,
        budget_eur: args.budget ?? null,
        board_enabled: args.boardEnabled ?? true,
        currency: shownCurrency(),
        fast_leagues: args.fastLeagues ?? [],
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

/** The user's saved tactics (api/routes.py tactics/presets). */
export interface TacticPreset {
  id: number
  name: string
  formation: string
  with_lineup: boolean // saved with its line-up
  saved: string // the game date
}

export const useTacticPresets = () =>
  useQuery({ queryKey: ['tactic-presets'], queryFn: () => api.get<TacticPreset[]>('/tactics/presets') })

export function useSaveTacticPreset() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; with_lineup: boolean }) => api.post<TacticPreset[]>('/tactics/presets', body),
    onSuccess: (data) => client.setQueryData(['tactic-presets'], data),
  })
}

export function useLoadTacticPreset() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.post<Tactics>(`/tactics/presets/${id}/load`, {}),
    onSuccess: (data) => client.setQueryData(['tactics', 'club'], data),
  })
}

export function useDeleteTacticPreset() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.delete<TacticPreset[]>(`/tactics/presets/${id}`),
    onSuccess: (data) => client.setQueryData(['tactic-presets'], data),
  })
}

/** The patch notes, fetched when the What's new window opens (`enabled`) and kept for a while. */
export const useChangelog = (enabled: boolean) =>
  useQuery({ queryKey: ['changelog'], queryFn: () => api.get<Changelog>('/changelog'), enabled, staleTime: 10 * 60_000, retry: 1 })

export const useDraft = (enabled = true) =>
  useQuery({ queryKey: ['draft'], queryFn: () => api.get<Draft>('/draft'), enabled, retry: false })

export function useDraftBoard() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (playerIds: number[]) => api.put<Draft>('/draft/board', { player_ids: playerIds }),
    onSuccess: (data) => qc.setQueryData(['draft'], data),
  })
}

export function useSignPick() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (playerId: number) => api.post<Draft>(`/draft/sign/${playerId}`),
    onSuccess: (data) => {
      qc.setQueryData(['draft'], data)
      void qc.invalidateQueries({ queryKey: ['squad'] })
    },
  })
}
