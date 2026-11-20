// High-school recruiting for a college coach (W9c; backend api/recruiting.py).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'
import type { ClubRef } from './types'

export type Priority = 'top' | 'high' | 'watch'
export type RecruitingPhase = 'before' | 'open' | 'late' | 'closed'

export interface Recruiting {
  class_season: number
  phase: RecruitingPhase
  start: string // offers open
  signing_day: string
  close: string // the class closes
  funding: number // the program's scholarship money, in full scholarships
  returning_money: number // held by next season's returning players
  class_money: number // committed and signed recruits'
  offered_money: number // open offers
  places: number // the roster limit
  returning: number
  class_count: number // committed and signed
  open_offers: number
  targets: number
  effort: number // the staff's week
  per_target: Record<Priority, number> // a week's effort on a target of each priority
  visits_used: number
  visits: number
  prestige: number
  offer_limit: number // open offers and the class together may be worth this much
}

export interface Range {
  low: number
  high: number
}

export interface Recruit {
  id: number
  name: string
  stars: number
  national_rank: number
  position: string
  position_rank: number
  state: string | null // home state; null for a recruit from abroad
  state_rank: number | null
  nation: string
  age: number
  overall: Range // the staff's estimate
  potential: Range
  knowledge: number // 0-1
  interest: number | null // in your program, 0-100
  priority: Priority | null // on your target list
  offer: number | null // your offer, a share of a full scholarship (0 a walk-on)
  offer_status: 'open' | 'pulled' | 'accepted' | 'declined' | null
  offers: number // programs offering him
  status: 'open' | 'committed' | 'signed' | 'enrolled' | 'gone'
  committed_to: ClubRef | null
  leader: ClubRef | null // who he leans towards, when your staff know
  hopes: number // the scholarship he hopes for
  wants: string[]
  top: { club: ClubRef; share: number }[] // his offers by preference, when known
  fit: 'good' | 'reach' | 'long_shot' | 'out_of_reach' // how he sees a program of your prestige
  expects: number // the program prestige he hopes for
}

export interface RecruitPage {
  total: number
  recruits: Recruit[]
}

export interface ClassRank {
  rank: number
  club: ClubRef
  recruits: number
  points: number
  stars: Record<string, number>
  mine: boolean
}

export interface RecruitFilters {
  view: 'board' | 'targets' | 'offers' | 'class'
  position: string | null
  state: string | null
  stars: number | null
  q: string
  openOnly: boolean
  realistic: boolean
  offset: number
  limit: number
}

const KEY = ['recruiting'] as const

export const useRecruiting = (enabled = true) => useQuery({ queryKey: [...KEY, 'summary'], queryFn: () => api.get<Recruiting>('/recruiting'), enabled })

export function useRecruits(f: RecruitFilters) {
  const params = new URLSearchParams({ view: f.view, offset: String(f.offset), limit: String(f.limit) })
  if (f.position) params.set('position', f.position)
  if (f.state) params.set('state', f.state)
  if (f.stars) params.set('stars', String(f.stars))
  if (f.q.trim()) params.set('q', f.q.trim())
  if (f.openOnly) params.set('open_only', 'true')
  if (f.realistic) params.set('realistic', 'true')
  return useQuery({ queryKey: [...KEY, 'recruits', params.toString()], queryFn: () => api.get<RecruitPage>(`/recruiting/recruits?${params}`), placeholderData: (prev) => prev })
}

export const useRecruit = (id: number | null) =>
  useQuery({ queryKey: [...KEY, 'recruit', id], queryFn: () => api.get<Recruit>(`/recruiting/recruits/${id}`), enabled: id !== null })

export const useClassRankings = (enabled = true) => useQuery({ queryKey: [...KEY, 'classes'], queryFn: () => api.get<ClassRank[]>('/recruiting/classes'), enabled })

function useRecruitAction<T, R>(fn: (arg: T) => Promise<R>) {
  const client = useQueryClient()
  return useMutation({ mutationFn: fn, onSuccess: () => void client.invalidateQueries({ queryKey: KEY }) })
}

export const useSetTarget = () => useRecruitAction(({ id, priority }: { id: number; priority: Priority | null }) => api.put<Recruit>(`/recruiting/targets/${id}`, { priority }))
export const useMakeOffer = () => useRecruitAction(({ id, share }: { id: number; share: number }) => api.put<Recruit>(`/recruiting/offers/${id}`, { share }))
export const usePullOffer = () => useRecruitAction((id: number) => api.delete<string[]>(`/recruiting/offers/${id}`))

// The GOD player (world/college/god_player.py): once every few seasons, a freshman with a pro's
// ratings at a random position, who stays four years.
export interface GodPlayer {
  available: boolean
  next_season: string | null
  every_seasons: number
  overall: number
  signed: ClubRef[] // the players (id, name), latest first
}

export const useGodPlayer = (enabled = true) => useQuery({ queryKey: [...KEY, 'god'], queryFn: () => api.get<GodPlayer>('/recruiting/god-player'), enabled })

export function useSignGodPlayer() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<GodPlayer>('/recruiting/god-player', {}),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: KEY })
      void client.invalidateQueries({ queryKey: ['squad'] })
      void client.invalidateQueries({ queryKey: ['career'] })
    },
  })
}
