import { Alert, Anchor, Badge, Button, Card, Group, Modal, NumberInput, SegmentedControl, Select, Stack, Switch, Table, Tabs, Text, TextInput, Title } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import { useCareer, useSquad, useWorldLeagues } from '../api/hooks'
import {
  type MarketPlayer,
  type OfferResult,
  type SearchFilters,
  useAnswerBid,
  useAskLoan,
  useBids,
  useExpiring,
  type AvailabilityStatus,
  useAvailability,
  useLoans,
  useMarketSearch,
  useRenew,
  useSetAvailability,
  useTransferHistory,
} from '../api/transfers'
import PlayerLink from '../components/PlayerLink'
import ClubLink from '../components/ClubLink'
import OfferModal from '../components/OfferModal'
import MarketOverview from '../components/MarketOverview'
import { useUrlState } from '../lib/urlState'
import { CURRENCIES, money, monthYear, shortDate, toEuros, useCurrency, wage } from '../lib/format'

const POSITIONS = ['GK', 'CB', 'FB', 'DM', 'CM', 'AM', 'W', 'ST']

function resultColor(result: OfferResult): string {
  return result.status === 'accepted' ? 'green' : result.status === 'countered' ? 'yellow' : 'red'
}

function LoanModal({ player, onClose }: { player: MarketPlayer; onClose: () => void }) {
  const ask = useAskLoan()
  const [share, setShare] = useState<string>('100')
  const [result, setResult] = useState<OfferResult | null>(null)
  return (
    <Modal opened onClose={onClose} title={`Borrow ${player.name}`} size="sm">
      <Stack>
        <Text size="sm" c="dimmed">
          Until the end of the season. His club lends only players it can spare, and he goes where he'll play.
        </Text>
        <Select
          label="You pay of his wage"
          data={[
            { value: '50', label: '50%' },
            { value: '75', label: '75%' },
            { value: '100', label: '100%' },
          ]}
          value={share}
          onChange={(v) => setShare(v ?? '100')}
          allowDeselect={false}
        />
        {result && (
          <Alert color={resultColor(result)} title={result.status === 'accepted' ? 'Done' : 'No deal'}>
            {result.message}
          </Alert>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            {result?.status === 'accepted' ? 'Close' : 'Cancel'}
          </Button>
          {result?.status !== 'accepted' && (
            <Button loading={ask.isPending} onClick={() => void ask.mutateAsync({ player_id: player.id, share: Number(share) / 100 }).then(setResult)}>
              Ask to borrow him
            </Button>
          )}
        </Group>
      </Stack>
    </Modal>
  )
}

function SearchTab() {
  const currency = useCurrency()
  const { symbol } = CURRENCIES[currency]
  const leagues = useWorldLeagues().data ?? []
  const navigate = useNavigate()
  // In the URL, so Back from a player's page brings the same form and the same results.
  const [form, setForm] = useUrlState<SearchFilters & { max_value_shown?: number }>('form', { min_overall: 60, max_overall: 99, max_age: 35 })
  const [filters, setFilters] = useUrlState<SearchFilters | null>('search', null)
  const [target, setTarget] = useState<MarketPlayer | null>(null)
  const [borrow, setBorrow] = useState<MarketPlayer | null>(null)
  const results = useMarketSearch(filters)
  const set = (patch: Partial<typeof form>) => setForm((current) => ({ ...current, ...patch }))

  return (
    <Stack>
      <Card withBorder>
        <Group align="end" wrap="wrap">
          <TextInput label="Name" value={form.name ?? ''} onChange={(e) => set({ name: e.currentTarget.value })} w={160} />
          <Select label="Position" data={POSITIONS} value={form.position ?? null} onChange={(v) => set({ position: v ?? undefined })} clearable w={110} />
          <NumberInput label="Overall from" value={form.min_overall} onChange={(v) => set({ min_overall: Number(v) || 0 })} w={110} />
          <NumberInput label="to" value={form.max_overall} onChange={(v) => set({ max_overall: Number(v) || 99 })} w={80} />
          <NumberInput label="Age up to" value={form.max_age} onChange={(v) => set({ max_age: Number(v) || 45 })} w={100} />
          <NumberInput label={`Value up to (${symbol}M)`} value={form.max_value_shown ?? ''} onChange={(v) => set({ max_value_shown: v === '' ? undefined : Number(v) })} w={150} />
          <Select
            label="League"
            data={leagues.map((l) => ({ value: l.key, label: l.name }))}
            value={form.league ?? null}
            onChange={(v) => set({ league: v ?? undefined })}
            clearable
            searchable
            w={190}
          />
          <Switch label="Free agents" checked={!!form.free_agents} onChange={(e) => set({ free_agents: e.currentTarget.checked })} />
          <Switch label="Listed only" checked={!!form.listed_only} onChange={(e) => set({ listed_only: e.currentTarget.checked })} />
          <Button
            onClick={() => {
              const { max_value_shown, ...rest } = form
              setFilters({ ...rest, max_value_eur: max_value_shown === undefined ? undefined : toEuros(max_value_shown * 1e6) })
            }}
          >
            Search
          </Button>
        </Group>
      </Card>
      {results.isFetching && <Text c="dimmed">Searching…</Text>}
      {results.data && results.data.length === 0 && <Text c="dimmed">Nobody matches.</Text>}
      {results.data && results.data.length > 0 && (
        <Table.ScrollContainer minWidth={760}>
          <Table highlightOnHover striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Player</Table.Th>
                <Table.Th>Pos</Table.Th>
                <Table.Th ta="right">Age</Table.Th>
                <Table.Th ta="right">OVR</Table.Th>
                <Table.Th>Club</Table.Th>
                <Table.Th ta="right">Value</Table.Th>
                <Table.Th>Contract</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {results.data.map((p) => (
                <Table.Tr key={p.id}>
                  <Table.Td>
                    <Anchor size="sm" onClick={() => void navigate({ to: '/players/$playerId', params: { playerId: String(p.id) } })}>
                      {p.name}
                    </Anchor>
                    {p.listed && (
                      <Badge ml={6} size="xs" color="orange" variant="light">
                        listed
                      </Badge>
                    )}
                  </Table.Td>
                  <Table.Td>{p.position}</Table.Td>
                  <Table.Td ta="right">{p.age}</Table.Td>
                  <Table.Td ta="right" fw={700}>
                    {p.overall}
                  </Table.Td>
                  <Table.Td>{p.club ? <ClubLink club={p.club} /> : <Text size="sm" c="dimmed">Free agent</Text>}</Table.Td>
                  <Table.Td ta="right">{money(p.value_eur)}</Table.Td>
                  <Table.Td>{p.contract_end ? monthYear(p.contract_end) : '–'}</Table.Td>
                  <Table.Td>
                    <Group gap={4} wrap="nowrap">
                      <Button size="xs" variant="light" onClick={() => setTarget(p)}>
                        {p.club ? 'Offer' : 'Sign'}
                      </Button>
                      {p.club && p.age <= 23 && (
                        <Button size="xs" variant="subtle" onClick={() => setBorrow(p)}>
                          Loan
                        </Button>
                      )}
                    </Group>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      {target && <OfferModal player={target} onClose={() => setTarget(null)} />}
      {borrow && <LoanModal player={borrow} onClose={() => setBorrow(null)} />}
    </Stack>
  )
}

function BidsTab() {
  const currency = useCurrency()
  const { symbol } = CURRENCIES[currency]
  const bids = useBids().data ?? []
  const answer = useAnswerBid()
  const [counter, setCounter] = useState<Record<number, number | string>>({})
  const [last, setLast] = useState<OfferResult | null>(null)
  return (
    <Stack>
      {last && (
        <Alert color={resultColor(last)} withCloseButton onClose={() => setLast(null)}>
          {last.message}
        </Alert>
      )}
      {bids.length === 0 && <Text c="dimmed">No offers for your players right now. Clubs bid during transfer windows.</Text>}
      {bids.map((b) => (
        <Card key={b.id} withBorder>
          <Group justify="space-between" wrap="wrap">
            <div>
              <Text fw={600}>
                <ClubLink club={b.bidder} /> want {b.player.name}
                {b.kind === 'loan' ? ' on loan' : ''}
              </Text>
              <Text size="sm" c="dimmed">
                {b.kind === 'loan'
                  ? `until the end of the season · they pay ${wage(b.wage_eur)} of his wage`
                  : `${money(b.fee_eur)} · he'd earn ${wage(b.wage_eur)} for ${b.years} ${b.years === 1 ? 'year' : 'years'}`}
                {` · answer by ${shortDate(b.expires)}`}
              </Text>
            </div>
            <Group gap="xs" align="end">
              <Button color="green" size="xs" loading={answer.isPending} onClick={() => void answer.mutateAsync({ id: b.id, action: 'accept' }).then(setLast)}>
                Accept
              </Button>
              <Button color="red" variant="light" size="xs" onClick={() => void answer.mutateAsync({ id: b.id, action: 'reject' }).then(setLast)}>
                Reject
              </Button>
              {b.kind !== 'loan' && (
                <>
                  <NumberInput size="xs" w={120} placeholder={`${symbol}M`} decimalScale={2} value={counter[b.id] ?? ''} onChange={(v) => setCounter({ ...counter, [b.id]: v })} />
                  <Button
                    size="xs"
                    variant="default"
                    disabled={counter[b.id] === undefined || counter[b.id] === ''}
                    onClick={() => void answer.mutateAsync({ id: b.id, action: 'counter', fee_eur: toEuros(Number(counter[b.id]) * 1e6) }).then(setLast)}
                  >
                    Counter
                  </Button>
                </>
              )}
            </Group>
          </Group>
        </Card>
      ))}
    </Stack>
  )
}

function SellTab() {
  const career = useCareer().data
  const squad = useSquad(career?.club.id).data ?? []
  const availability = useAvailability().data
  const setAvailability = useSetAvailability()
  const names = new Map(squad.map((p) => [p.id, p.name]))
  const statusOf = (id: number): AvailabilityStatus => (availability?.transfer.includes(id) ? 'transfer' : availability?.loan.includes(id) ? 'loan' : 'none')
  const lists: { title: string; hint: string; ids: number[] }[] = [
    { title: 'Transfer list', hint: 'Clubs bid to buy these players.', ids: availability?.transfer ?? [] },
    { title: 'Loan list', hint: 'Clubs that need cover ask to borrow these players for the season.', ids: availability?.loan ?? [] },
  ]
  const loans = useLoans().data ?? []
  return (
    <Stack>
      {loans.length > 0 && (
        <Card withBorder>
          <Text fw={600} mb="xs">
            Loans
          </Text>
          <Table>
            <Table.Tbody>
              {loans.map((l) => (
                <Table.Tr key={l.player.id}>
                  <Table.Td>{l.player.name}</Table.Td>
                  <Table.Td>{l.yours_out ? <>at <ClubLink club={l.borrower} /></> : <>from <ClubLink club={l.parent} /></>}</Table.Td>
                  <Table.Td>until {shortDate(l.end)}</Table.Td>
                  <Table.Td ta="right">{wage(l.wage_eur)} paid by {l.yours_out ? 'them' : 'you'}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Card>
      )}
      {lists.map((l) => (
        <Card withBorder key={l.title}>
          <Text fw={600}>{l.title}</Text>
          <Text size="xs" c="dimmed" mb="xs">
            {l.hint} Offers arrive under &ldquo;Offers for your players&rdquo; over the following days while the window is open.
          </Text>
          {l.ids.length === 0 && (
            <Text size="sm" c="dimmed">
              Nobody.
            </Text>
          )}
          {l.ids.map((id) => (
            <Group key={id} justify="space-between">
              <Text size="sm">
                <PlayerLink player={{ id, name: names.get(id) ?? `Player ${id}` }} />
              </Text>
              <Button size="compact-xs" variant="default" loading={setAvailability.isPending} onClick={() => setAvailability.mutate({ playerId: id, status: 'none' })}>
                Remove
              </Button>
            </Group>
          ))}
        </Card>
      ))}
      <Table striped>
        <Table.Tbody>
          {squad.map((p) => (
            <Table.Tr key={p.id}>
              <Table.Td>
                <PlayerLink player={p} />
              </Table.Td>
              <Table.Td>{p.position}</Table.Td>
              <Table.Td ta="right">{p.overall}</Table.Td>
              <Table.Td ta="right">{money(p.value_eur)}</Table.Td>
              <Table.Td>
                <SegmentedControl
                  size="xs"
                  value={statusOf(p.id)}
                  disabled={!availability}
                  onChange={(v) => setAvailability.mutate({ playerId: p.id, status: v as AvailabilityStatus })}
                  data={[
                    { value: 'none', label: 'Not for sale' },
                    { value: 'transfer', label: 'Transfer' },
                    { value: 'loan', label: 'Loan' },
                  ]}
                />
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  )
}

function ContractsTab() {
  const currency = useCurrency()
  const { symbol, perEuro } = CURRENCIES[currency]
  const expiring = useExpiring().data ?? []
  const renewal = useRenew()
  const [wages, setWages] = useState<Record<number, number | string>>({})
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)
  return (
    <Stack>
      <Text size="sm" c="dimmed">
        These players' contracts end on 30 June. Renew the ones you want to keep; the others leave as free agents.
      </Text>
      {note && (
        <Alert color={note.ok ? 'green' : 'red'} withCloseButton onClose={() => setNote(null)}>
          {note.text}
        </Alert>
      )}
      {expiring.length === 0 && <Text c="dimmed">No contracts end this season.</Text>}
      <Table striped>
        <Table.Tbody>
          {expiring.map((e) => {
            const shown = wages[e.player_id] ?? Math.round((e.asks_eur * perEuro) / 100) / 10
            return (
              <Table.Tr key={e.player_id}>
                <Table.Td>{e.name}</Table.Td>
                <Table.Td ta="right">{e.age}</Table.Td>
                <Table.Td ta="right" fw={700}>
                  {e.overall}
                </Table.Td>
                <Table.Td>now {wage(e.wage_eur)}</Table.Td>
                <Table.Td>
                  {e.willing ? `asks ${wage(e.asks_eur)} for ${e.years} ${e.years === 1 ? 'year' : 'years'}` : <Text c="red" size="sm">won't sign</Text>}
                </Table.Td>
                <Table.Td>
                  <Group gap="xs" wrap="nowrap">
                    <NumberInput size="xs" w={110} decimalScale={1} disabled={!e.willing} value={shown} onChange={(v) => setWages({ ...wages, [e.player_id]: v })} rightSection={<Text size="xs">{symbol}K</Text>} />
                    <Button
                      size="xs"
                      disabled={!e.willing}
                      loading={renewal.isPending}
                      onClick={() =>
                        void renewal
                          .mutateAsync({ playerId: e.player_id, wage_eur: toEuros(Number(shown) * 1e3) })
                          .then((r) => setNote({ ok: true, text: r.message }), (err: Error) => setNote({ ok: false, text: err.message }))
                      }
                    >
                      Renew
                    </Button>
                  </Group>
                </Table.Td>
              </Table.Tr>
            )
          })}
        </Table.Tbody>
      </Table>
    </Stack>
  )
}

function HistoryTab() {
  const [mine, setMine] = useState(true)
  const rows = useTransferHistory(mine).data ?? []
  return (
    <Stack>
      <Switch label="Only your club's" checked={mine} onChange={(e) => setMine(e.currentTarget.checked)} />
      {rows.length === 0 && <Text c="dimmed">No moves yet.</Text>}
      <Table striped>
        <Table.Tbody>
          {rows.map((r, i) => (
            <Table.Tr key={`${r.date}-${r.player.id}-${i}`} fw={r.yours ? 600 : undefined}>
              <Table.Td w={90} c="dimmed">
                {shortDate(r.date)}
              </Table.Td>
              <Table.Td>{r.player.name}</Table.Td>
              <Table.Td>{r.from_club ? <ClubLink club={r.from_club} /> : 'Free agent'}</Table.Td>
              <Table.Td>→ {r.to_club ? <ClubLink club={r.to_club} /> : 'released'}</Table.Td>
              <Table.Td ta="right">{r.kind === 'transfer' ? money(r.fee_eur) : r.kind === 'free' ? 'free' : ''}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  )
}

export default function TransfersPage() {
  const bids = useBids().data ?? []
  const [tab, setTab] = useUrlState<string | null>('tab', null)
  return (
    <Stack>
      <Title order={2}>Transfers</Title>
      <Tabs value={tab ?? (bids.length ? 'bids' : 'search')} onChange={setTab} keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="search">Find players</Tabs.Tab>
          <Tabs.Tab value="bids" rightSection={bids.length ? <Badge size="xs" color="orange">{bids.length}</Badge> : undefined}>
            Offers for your players
          </Tabs.Tab>
          <Tabs.Tab value="market">Market overview</Tabs.Tab>
          <Tabs.Tab value="sell">Sell</Tabs.Tab>
          <Tabs.Tab value="contracts">Contracts</Tabs.Tab>
          <Tabs.Tab value="history">History</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="search" pt="md">
          <SearchTab />
        </Tabs.Panel>
        <Tabs.Panel value="bids" pt="md">
          <BidsTab />
        </Tabs.Panel>
        <Tabs.Panel value="market" pt="md">
          <MarketOverview />
        </Tabs.Panel>
        <Tabs.Panel value="sell" pt="md">
          <SellTab />
        </Tabs.Panel>
        <Tabs.Panel value="contracts" pt="md">
          <ContractsTab />
        </Tabs.Panel>
        <Tabs.Panel value="history" pt="md">
          <HistoryTab />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  )
}
