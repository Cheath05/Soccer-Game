// The user's transfer market (W4-6): search, terms, offers, bids for the user's players,
// listing and history. Money in euros, as the server keeps it.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from './client'
import type { ClubRef } from './types'

export interface MarketPlayer {
  id: number
  name: string
  age: number
  position: string
  overall: number
  club: ClubRef | null
  league: string | null
  value_eur: number
  contract_end: string | null
  listed: boolean
}

export interface Terms {
  player_id: number
  value_eur: number
  wage_eur: number
  years: number
  listed: boolean
  free_agent: boolean
  window_open: boolean
  // Added by the backend alongside the offer screen; optional so older servers still work.
  budget_eur?: number
  weeks_left?: number
  max_rounds?: number
  talks?: Talks | null
}

export interface Talks {
  their_price_eur: number
  your_last_bid_eur: number
  rounds_used: number
  rounds_left: number
  final: boolean
  ended: boolean
}

export interface OfferResult {
  status: 'accepted' | 'countered' | 'rejected' | 'refused'
  message: string
  fee_eur: number
  wage_eur: number
  years: number
  final?: boolean
  rounds_left?: number
  ended?: boolean // the club has ended talks for this window
}

export interface Bid {
  id: number
  kind: 'transfer' | 'loan' // a loan: they ask to borrow him to the season's end; wage_eur is their share
  player: ClubRef
  bidder: ClubRef
  fee_eur: number
  wage_eur: number
  years: number
  expires: string
}

export interface HistoryRow {
  date: string
  player: ClubRef
  from_club: ClubRef | null
  to_club: ClubRef | null
  kind: string
  fee_eur: number
  yours: boolean
}

export interface SearchFilters {
  position?: string
  min_overall?: number
  max_overall?: number
  max_age?: number
  max_value_eur?: number
  league?: string
  free_agents?: boolean
  listed_only?: boolean
  name?: string
}

function query(filters: SearchFilters): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '' && value !== false) params.set(key, String(value))
  }
  return params.toString()
}

export const useMarketSearch = (filters: SearchFilters | null) =>
  useQuery({
    queryKey: ['market-search', filters],
    queryFn: () => api.get<MarketPlayer[]>(`/transfers/search?${query(filters ?? {})}`),
    enabled: filters !== null,
  })

export const useTerms = (playerId: number | null) =>
  useQuery({
    queryKey: ['terms', playerId],
    queryFn: () => api.get<Terms>(`/transfers/terms/${playerId}`),
    enabled: playerId !== null,
  })

export const useBids = () => useQuery({ queryKey: ['bids'], queryFn: () => api.get<Bid[]>('/transfers/bids') })

export const useListed = () => useQuery({ queryKey: ['listed'], queryFn: () => api.get<number[]>('/transfers/listed') })

export const useTransferHistory = (mine: boolean) =>
  useQuery({ queryKey: ['transfer-history', mine], queryFn: () => api.get<HistoryRow[]>(`/transfers/history?mine=${mine}`) })

/** Anything that moves a player invalidates every cached view (squads, finances, the market). */
function useInvalidate() {
  const client = useQueryClient()
  return () => client.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'world-leagues' })
}

export function useMakeOffer() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (body: { player_id: number; fee_eur: number; wage_eur?: number; years?: number }) =>
      api.post<OfferResult>('/transfers/offer', body),
    onSuccess: (result) => {
      if (result.status === 'accepted') void invalidate()
    },
  })
}

export function useAnswerBid() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (args: { id: number; action: 'accept' | 'reject' | 'counter'; fee_eur?: number }) =>
      api.post<OfferResult>(`/transfers/bids/${args.id}`, { action: args.action, fee_eur: args.fee_eur ?? null }),
    onSuccess: () => void invalidate(),
  })
}

export function useSetListed() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (args: { playerId: number; listed: boolean }) =>
      api.put<{ listed: boolean }>(`/transfers/listed/${args.playerId}?listed=${args.listed}`, {}),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['listed'] }),
  })
}

export interface Availability {
  transfer: number[]
  loan: number[]
}
export type AvailabilityStatus = 'none' | 'transfer' | 'loan'

export const useAvailability = () =>
  useQuery({ queryKey: ['availability'], queryFn: () => api.get<Availability>('/transfers/availability') })

export function useSetAvailability() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (args: { playerId: number; status: AvailabilityStatus }) =>
      api.put<Availability>(`/transfers/availability/${args.playerId}`, { status: args.status }),
    onSuccess: () => {
      for (const key of ['availability', 'listed', 'squad', 'player']) void client.invalidateQueries({ queryKey: [key] })
    },
  })
}

export interface Expiring {
  player_id: number
  name: string
  age: number
  overall: number
  end_date: string
  wage_eur: number
  asks_eur: number
  years: number
  willing: boolean
}

export const useExpiring = () => useQuery({ queryKey: ['expiring'], queryFn: () => api.get<Expiring[]>('/transfers/contracts') })

export function useRenew() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (args: { playerId: number; wage_eur?: number; years?: number }) =>
      api.post<{ message: string }>(`/transfers/contracts/${args.playerId}/renew`, { wage_eur: args.wage_eur ?? null, years: args.years ?? null }),
    onSuccess: () => void invalidate(),
  })
}

export interface LoanRow {
  player: ClubRef
  parent: ClubRef
  borrower: ClubRef
  end: string
  wage_eur: number
  yours_out: boolean
}

export const useLoans = () => useQuery({ queryKey: ['loans'], queryFn: () => api.get<LoanRow[]>('/transfers/loans') })

export function useAskLoan() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (body: { player_id: number; share: number }) => api.post<OfferResult>('/transfers/loan', body),
    onSuccess: (result) => {
      if (result.status === 'accepted') void invalidate()
    },
  })
}

export interface OverviewPlayer {
  player: ClubRef
  age: number
  position: string
  overall: number
  club: ClubRef | null
  value_eur: number
}

export interface OverviewTransfer {
  date: string
  player: ClubRef
  age: number | null
  position: string | null
  overall: number | null
  from_club: ClubRef | null
  to_club: ClubRef | null
  fee_eur: number
  yours: boolean
}

export interface OverviewProspect extends OverviewPlayer {
  potential_low: number
  potential_high: number
  potential_label: string
}

export interface MarketOverview {
  season: string
  biggest_transfers: OverviewTransfer[]
  most_valuable: OverviewPlayer[]
  prospects: OverviewProspect[]
}

/** The world's biggest moves this season, most valuable players and best young prospects. */
export const useMarketOverview = () => useQuery({ queryKey: ['market-overview'], queryFn: () => api.get<MarketOverview>('/market/overview') })
