// The Americas (W9a): MLS's roster rules for the user's club (api/mls.py) and US college soccer
// (api/college.py). Money in euros a year, as the server keeps it.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, api } from './client'
import type { ClubRef } from './types'

// --- MLS --------------------------------------------------------------------------------------

export type Designation = 'senior' | 'supplemental' | 'dp' | 'u22' | 'homegrown' | 'generation_adidas'

export interface MlsCharge {
  base_eur: number // before allocation money
  tam_eur: number // bought down with TAM
  gam_eur: number // bought down with GAM
  charge_eur: number // against the budget
}

export interface MlsPlayer {
  id: number
  name: string
  age: number
  position: string
  overall: number
  salary_eur: number // a year
  designation: Designation
  roster: 'senior' | 'supplemental'
  international: boolean
  canadian: boolean
  homegrown: boolean
  generation_adidas: boolean
  loan: 'in' | 'out' | null
  charge: MlsCharge
  options: string[] // "designation:roster" pairs he may take
}

export interface MlsRoster {
  club: ClubRef
  yours: boolean
  season_id: number
  roster_model: number
  model_choosable: boolean
  usd_per_euro: number
  budget_eur: number
  budget_used_eur: number
  budget_left_eur: number
  max_charge_eur: number
  empty_senior_slots_charged: number
  allocation: {
    tam_eur: number
    tam_used_eur: number
    tam_left_eur: number
    gam_eur: number
    gam_expiring_eur: number
    gam_used_eur: number
    gam_left_eur: number
  }
  slots: {
    senior: number
    senior_slots: number
    supplemental: number
    supplemental_slots: number
    designated_players: number
    designated_slots: number
    u22: number
    u22_slots: number
    internationals: number
    international_slots: number
  }
  compliant: boolean
  problems: string[]
  adding_blocked: boolean
  players: MlsPlayer[]
}

export interface SlotSellers {
  price_eur: number
  gam_left_eur: number
  sellers: { club: ClubRef; spare: number }[]
}

export const MLS_LEAGUE = 'USA1'

export const useMlsRoster = (enabled = true) =>
  useQuery({
    queryKey: ['mls-roster'],
    queryFn: () => api.get<MlsRoster>('/mls/roster'),
    enabled,
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2,
  })

export const useSlotSellers = (enabled: boolean) =>
  useQuery({ queryKey: ['mls-slot-sellers'], queryFn: () => api.get<SlotSellers>('/mls/international-slot'), enabled })

/** The user's roster choices: each answers the roster as it now stands (409 with the rule that
 * blocks it). */
function useRosterAction<T>(method: 'put' | 'post', path: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: T) => (method === 'put' ? api.put<MlsRoster>(path, body) : api.post<MlsRoster>(path, body)),
    onSuccess: (data) => {
      client.setQueryData(['mls-roster'], data)
      void client.invalidateQueries({ queryKey: ['mls-slot-sellers'] })
    },
  })
}

export const useSetDesignation = () =>
  useRosterAction<{ player_id: number; designation: Designation; roster?: string }>('put', '/mls/designation')
export const useSetRosterModel = () => useRosterAction<{ model: number }>('put', '/mls/roster-model')
export const useBuySlot = () => useRosterAction<{ from_club_id: number }>('post', '/mls/international-slot')

// --- college ----------------------------------------------------------------------------------

// A team's record over every college game this season: conference, non-conference and tournaments.
export interface CollegeRecord {
  played: number
  won: number
  drawn: number
  lost: number
  goals_for: number
  goals_against: number
}

export interface ConferenceRow {
  position: number
  club: ClubRef
  played: number
  won: number
  drawn: number
  lost: number
  goals_for: number
  goals_against: number
  points: number
  in_tournament: boolean
  overall?: CollegeRecord // every college game, not only the conference's
}

export interface Conference {
  key: string
  name: string
  short_name: string
  tournament: number // teams in its tournament; 0: none
  regular_season_champion: ClubRef | null
  tournament_champion: ClubRef | null
  rows: ConferenceRow[]
}

export interface Ranking {
  rank: number
  club: ClubRef
  conference: string
  rpi: number
  overall?: CollegeRecord
}

/** A record as W-D-L. */
export const wdl = (r?: CollegeRecord) => (r ? `${r.won}-${r.drawn}-${r.lost}` : '–')

export interface BracketSide {
  seed: number
  club: ClubRef
}

export interface BracketMatch {
  index: number
  a: BracketSide | null
  b: BracketSide | null
  bye: boolean
  fixture_id: number | null
  date: string | null
  neutral: boolean
  home_goals: number | null
  away_goals: number | null
  home_pens: number | null
  away_pens: number | null
  extra_time: boolean
  home_club_id: number | null
  winner: BracketSide | null
}

export interface BracketRound {
  round: number
  name: string
  date: string
  matches: BracketMatch[]
}

export interface Bracket {
  event: string
  name: string
  season: string
  seeded: number
  entrants: { seed: number; club: ClubRef; conference: string; bid: string | null; rank: number | null; rpi: number | null }[]
  rounds: BracketRound[]
  champion: ClubRef | null
}

export interface Prospect {
  player_id: number
  name: string
  college: ClubRef
  class_year: string
  age: number
  position: string
  overall: number
  potential: number // hidden: not shown
  ga: boolean
}

const noRetryOn404 = (count: number, error: Error) => !(error instanceof ApiError && error.status === 404) && count < 2

export const useConferences = (enabled = true) =>
  useQuery({ queryKey: ['college', 'conferences'], queryFn: () => api.get<Conference[]>('/college/conferences'), retry: noRetryOn404, enabled })

export const useRankings = (enabled: boolean) =>
  useQuery({ queryKey: ['college', 'rankings'], queryFn: () => api.get<Ranking[]>('/college/rankings?limit=50'), enabled, retry: noRetryOn404 })

export const useBracket = (event: string, enabled: boolean) =>
  useQuery({
    queryKey: ['college', 'bracket', event],
    queryFn: () => api.get<Bracket>(`/college/bracket?event=${encodeURIComponent(event)}`),
    enabled,
    retry: noRetryOn404,
  })

export const useDraftPool = (enabled: boolean) =>
  useQuery({ queryKey: ['college', 'draft-pool'], queryFn: () => api.get<Prospect[]>('/college/draft-pool'), enabled, retry: noRetryOn404 })
