import { Alert, Anchor, Badge, Button, Card, Group, Modal, NumberInput, Select, Stack, Switch, Table, Tabs, Text, TextInput, Title } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'
import { useState } from 'react'

import { useCareer, useSquad, useWorldLeagues } from '../api/hooks'
import {
  type MarketPlayer,
  type OfferResult,
  type SearchFilters,
  useAnswerBid,
  useBids,
  useExpiring,
  useListed,
  useMakeOffer,
  useMarketSearch,
  useRenew,
  useSetListed,
  useTerms,
  useTransferHistory,
} from '../api/transfers'
import ClubLink from '../components/ClubLink'
import { CURRENCIES, money, monthYear, shortDate, toEuros, useCurrency, wage } from '../lib/format'

const POSITIONS = ['GK', 'CB', 'FB', 'DM', 'CM', 'AM', 'W', 'ST']

function resultColor(result: OfferResult): string {
  return result.status === 'accepted' ? 'green' : result.status === 'countered' ? 'yellow' : 'red'
}

/** Amounts are typed in the shown currency, in millions or thousands, and sent in euros. */
function shownFromEuros(eur: number, perEuro: number, scale: number): number {
  return Math.round((eur * perEuro) / scale * 100) / 100
}

function OfferModal({ player, onClose }: { player: MarketPlayer; onClose: () => void }) {
  const currency = useCurrency()
  const { symbol, perEuro } = CURRENCIES[currency]
  const terms = useTerms(player.id).data
  const offer = useMakeOffer()
  const [fee, setFee] = useState<number | string>('')
  const [weekly, setWeekly] = useState<number | string>('')
  const [result, setResult] = useState<OfferResult | null>(null)
  const free = player.club === null
  const feeShown = fee === '' ? (terms && !free ? shownFromEuros(terms.value_eur, perEuro, 1e6) : 0) : Number(fee)
  const wageShown = weekly === '' ? (terms ? shownFromEuros(terms.wage_eur, perEuro, 1e3) : 0) : Number(weekly)

  const send = (feeEuros?: number) => {
    void offer
      .mutateAsync({
        player_id: player.id,
        fee_eur: free ? 0 : (feeEuros ?? toEuros(feeShown * 1e6)),
        wage_eur: toEuros(wageShown * 1e3),
      })
      .then(setResult)
  }

  return (
    <Modal opened onClose={onClose} title={`Sign ${player.name}`} size="md">
      <Stack>
        {terms && (
          <Text size="sm" c="dimmed">
            Value {money(terms.value_eur)} · asks {wage(terms.wage_eur)} for {terms.years} {terms.years === 1 ? 'year' : 'years'}
            {terms.listed ? ' · listed for sale' : ''}
          </Text>
        )}
        {terms && !terms.window_open && <Alert color="orange">Your transfer window is closed.</Alert>}
        {!free && (
          <NumberInput label={`Fee (${symbol}M)`} min={0} decimalScale={2} value={feeShown} onChange={setFee} />
        )}
        <NumberInput label={`Wage (${symbol}K a week)`} min={0} decimalScale={1} value={wageShown} onChange={setWeekly} />
        {result && (
          <Alert color={resultColor(result)} title={result.status === 'accepted' ? 'Done' : result.status === 'countered' ? 'They want more' : 'No deal'}>
            {result.message}
            {result.status === 'countered' && (
              <Button size="xs" mt="xs" onClick={() => send(result.fee_eur)}>
                Offer {money(result.fee_eur)}
              </Button>
            )}
          </Alert>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            {result?.status === 'accepted' ? 'Close' : 'Cancel'}
          </Button>
          {result?.status !== 'accepted' && (
            <Button loading={offer.isPending} onClick={() => send()}>
              {free ? 'Offer a contract' : 'Make the offer'}
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
  const [form, setForm] = useState<SearchFilters & { max_value_shown?: number }>({ min_overall: 60, max_overall: 99, max_age: 35 })
  const [filters, setFilters] = useState<SearchFilters | null>(null)
  const [target, setTarget] = useState<MarketPlayer | null>(null)
  const results = useMarketSearch(filters)
  const set = (patch: Partial<typeof form>) => setForm({ ...form, ...patch })

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
                    <Button size="xs" variant="light" onClick={() => setTarget(p)}>
                      {p.club ? 'Offer' : 'Sign'}
                    </Button>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      {target && <OfferModal player={target} onClose={() => setTarget(null)} />}
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
              </Text>
              <Text size="sm" c="dimmed">
                {money(b.fee_eur)} · he'd earn {wage(b.wage_eur)} for {b.years} {b.years === 1 ? 'year' : 'years'} · answer by {shortDate(b.expires)}
              </Text>
            </div>
            <Group gap="xs" align="end">
              <Button color="green" size="xs" loading={answer.isPending} onClick={() => void answer.mutateAsync({ id: b.id, action: 'accept' }).then(setLast)}>
                Accept
              </Button>
              <Button color="red" variant="light" size="xs" onClick={() => void answer.mutateAsync({ id: b.id, action: 'reject' }).then(setLast)}>
                Reject
              </Button>
              <NumberInput size="xs" w={120} placeholder={`${symbol}M`} decimalScale={2} value={counter[b.id] ?? ''} onChange={(v) => setCounter({ ...counter, [b.id]: v })} />
              <Button
                size="xs"
                variant="default"
                disabled={counter[b.id] === undefined || counter[b.id] === ''}
                onClick={() => void answer.mutateAsync({ id: b.id, action: 'counter', fee_eur: toEuros(Number(counter[b.id]) * 1e6) }).then(setLast)}
              >
                Counter
              </Button>
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
  const listed = new Set(useListed().data ?? [])
  const setListed = useSetListed()
  return (
    <Stack>
      <Text size="sm" c="dimmed">
        Listed players are offered to other clubs at a lower price, and clubs come in for them more readily.
      </Text>
      <Table striped>
        <Table.Tbody>
          {squad.map((p) => (
            <Table.Tr key={p.id}>
              <Table.Td>{p.name}</Table.Td>
              <Table.Td>{p.position}</Table.Td>
              <Table.Td ta="right">{p.overall}</Table.Td>
              <Table.Td ta="right">{money(p.value_eur)}</Table.Td>
              <Table.Td>
                <Switch
                  label="For sale"
                  checked={listed.has(p.id)}
                  onChange={(e) => setListed.mutate({ playerId: p.id, listed: e.currentTarget.checked })}
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
  return (
    <Stack>
      <Title order={2}>Transfers</Title>
      <Tabs defaultValue={bids.length ? 'bids' : 'search'} keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="search">Find players</Tabs.Tab>
          <Tabs.Tab value="bids" rightSection={bids.length ? <Badge size="xs" color="orange">{bids.length}</Badge> : undefined}>
            Offers for your players
          </Tabs.Tab>
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
