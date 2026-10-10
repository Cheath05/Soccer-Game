// The transfer-offer screen: fee, contract, what it costs you, and the haggling so far.
// All API amounts are euros. Amounts the server gives us ("their price", "his wage") are sent
// back unchanged; only what the user types is converted from the shown currency.
import { Alert, Badge, Button, Card, Divider, Group, Modal, NumberInput, Select, Stack, Text, Timeline } from '@mantine/core'
import { useState } from 'react'

import { type MarketPlayer, type OfferResult, useMakeOffer, useTerms } from '../api/transfers'
import { CURRENCIES, money, positionColor, toEuros, useCurrency, wage } from '../lib/format'

interface Round {
  bid: number
  result: OfferResult
}

/** An amount field typed in the shown currency (scaled), or set exactly in euros by a button. */
function useEuroField(defaultEur: number, perEuro: number, scale: number) {
  const [typed, setTyped] = useState<number | string | null>(null)
  const [exact, setExact] = useState<number | null>(null)
  const eur = typed !== null ? toEuros(Number(typed) * scale) : (exact ?? defaultEur)
  const value = typed !== null ? typed : Math.round(((exact ?? defaultEur) * perEuro) / scale * 100) / 100
  return {
    eur,
    value,
    touched: typed !== null || exact !== null,
    onChange: (v: number | string) => {
      setTyped(v)
      setExact(null)
    },
    set: (euros: number) => {
      setTyped(null)
      setExact(euros)
    },
  }
}

function Dots({ left, max }: { left: number; max: number }) {
  return (
    <Group gap={4} aria-label={`${left} of ${max} rounds left`}>
      {Array.from({ length: max }, (_, i) => (
        <span
          key={i}
          style={{
            width: 10,
            height: 10,
            borderRadius: '50%',
            background: i < left ? 'var(--mantine-color-green-6)' : 'var(--mantine-color-gray-4)',
          }}
        />
      ))}
    </Group>
  )
}

function Line({ label, value, strong, color }: { label: string; value: string; strong?: boolean; color?: string }) {
  return (
    <Group justify="space-between" wrap="nowrap">
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text size="sm" fw={strong ? 700 : 500} c={color}>
        {value}
      </Text>
    </Group>
  )
}

export default function OfferModal({ player, onClose }: { player: MarketPlayer; onClose: () => void }) {
  const { perEuro, symbol } = CURRENCIES[useCurrency()]
  const terms = useTerms(player.id).data
  const offer = useMakeOffer()
  const [rounds, setRounds] = useState<Round[]>([])
  const [years, setYears] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const free = player.club === null || terms?.free_agent === true
  const last = rounds.length > 0 ? rounds[rounds.length - 1].result : null
  // A refusal (over budget, window shut) isn't a round of talks: where talks stand is the last
  // answer that was one (its price, rounds left, final or not).
  const lastTalk = [...rounds].reverse().find((r) => r.result.status !== 'refused')?.result ?? null
  const talks = terms?.talks ?? null
  const maxRounds = terms?.max_rounds ?? 4
  const theirPrice = lastTalk && lastTalk.status !== 'accepted' && lastTalk.fee_eur > 0 ? lastTalk.fee_eur : (talks?.their_price_eur ?? null)
  const roundsLeft = lastTalk?.rounds_left ?? talks?.rounds_left ?? maxRounds
  const isFinal = lastTalk ? lastTalk.final === true : (talks?.final ?? false)
  const ended = (last?.ended ?? false) || (talks?.ended ?? false)
  const accepted = last?.status === 'accepted'

  const fee = useEuroField(talks?.their_price_eur ?? terms?.value_eur ?? 0, perEuro, 1e6)
  const pay = useEuroField(terms?.wage_eur ?? 0, perEuro, 1e3)
  const yearsValue = Number(years ?? terms?.years ?? 1)

  const feeEur = free ? 0 : fee.eur
  const wageEur = pay.eur
  const season = wageEur * (terms?.weeks_left ?? 0)
  const total = feeEur + season
  const over = terms?.budget_eur !== undefined && total > terms.budget_eur
  const value = terms?.value_eur ?? 0
  const pct = value > 0 ? Math.round((feeEur / value) * 100) : 0

  const send = (feeSent: number) => {
    setError(null)
    offer
      .mutateAsync({ player_id: player.id, fee_eur: free ? 0 : feeSent, wage_eur: wageEur, years: yearsValue })
      .then((result) => {
        setRounds((r) => [...r, { bid: feeSent, result }])
        if (result.status === 'countered' || result.status === 'rejected') {
          if (result.fee_eur > 0) fee.set(result.fee_eur)
        }
      })
      .catch((e: Error) => setError(e.message))
  }

  const closed = terms !== undefined && !terms.window_open
  const disabled = ended || closed || !terms
  const answerColor = (r: OfferResult) => (r.status === 'accepted' ? 'green' : r.status === 'countered' ? 'yellow' : 'red')

  return (
    <Modal opened onClose={onClose} title={`Sign ${player.name}`} size="lg">
      <Stack>
        <Group justify="space-between" align="center">
          <div>
            <Text fw={700} size="lg">
              {player.name}
            </Text>
            <Text size="sm" c="dimmed">
              {player.age} years · {player.club ? player.club.name : 'Free agent'}
              {terms?.listed ? ' · listed for sale' : ''}
            </Text>
          </div>
          <Group gap="xs">
            <Badge color={positionColor(player.position)}>{player.position}</Badge>
            <Badge variant="outline" size="lg">
              {player.overall}
            </Badge>
          </Group>
        </Group>

        {closed && <Alert color="orange">Your transfer window is closed.</Alert>}

        {accepted && last ? (
          <Alert color="green" title="Deal done">
            {last.message}
          </Alert>
        ) : (
          <>
            {!free && (
              <Card withBorder padding="sm">
                <Text fw={600} mb={4}>
                  Fee
                </Text>
                <Group align="flex-end" gap="md">
                  <NumberInput
                    label={`Your bid (${symbol}M)`}
                    min={0}
                    decimalScale={2}
                    value={fee.value}
                    onChange={fee.onChange}
                    disabled={disabled}
                    w={160}
                  />
                  <Stack gap={0}>
                    <Text size="xs" c="dimmed">
                      Value {money(value)}
                    </Text>
                    <Text size="sm" fw={600} c={pct < 60 ? 'red' : pct < 100 ? 'yellow.8' : undefined}>
                      {pct}% of value
                    </Text>
                  </Stack>
                </Group>
                <Group gap={6} mt="xs">
                  {[80, 90, 100].map((p) => (
                    <Button key={p} size="compact-xs" variant="light" disabled={disabled} onClick={() => fee.set(Math.round((value * p) / 100))}>
                      {p}% of value
                    </Button>
                  ))}
                  {theirPrice !== null && (
                    <Button size="compact-xs" variant="light" color="yellow" disabled={disabled} onClick={() => fee.set(theirPrice)}>
                      Their price {money(theirPrice)}
                    </Button>
                  )}
                </Group>
              </Card>
            )}

            <Card withBorder padding="sm">
              <Text fw={600} mb={4}>
                Contract
              </Text>
              <Group align="flex-end" gap="md">
                <NumberInput
                  label={`Weekly wage (${symbol}K)`}
                  min={0}
                  decimalScale={1}
                  value={pay.value}
                  onChange={pay.onChange}
                  disabled={disabled}
                  w={160}
                />
                <Select
                  label="Years"
                  data={[1, 2, 3, 4, 5].map((y) => String(y))}
                  value={String(yearsValue)}
                  onChange={setYears}
                  allowDeselect={false}
                  disabled={disabled}
                  w={90}
                />
                {terms && (
                  <Text size="xs" c="dimmed">
                    He asks {wage(terms.wage_eur)} for {terms.years} {terms.years === 1 ? 'year' : 'years'}
                  </Text>
                )}
              </Group>
              {last?.status === 'rejected' && last.wage_eur > 0 && (
                <Group gap="xs" mt="xs">
                  <Text size="sm">He asks {wage(last.wage_eur)}.</Text>
                  <Button size="compact-xs" variant="light" disabled={disabled} onClick={() => pay.set(last.wage_eur)}>
                    Pay his wage
                  </Button>
                </Group>
              )}
            </Card>

            <Card withBorder padding="sm">
              <Text fw={600} mb={4}>
                What it costs
              </Text>
              <Stack gap={2}>
                {!free && <Line label="Fee" value={money(feeEur)} />}
                {terms?.weeks_left !== undefined && (
                  <Line label={`Wages this season (${terms.weeks_left} weeks)`} value={money(season)} />
                )}
                <Line label="Total now" value={money(total)} strong color={over ? 'red' : undefined} />
                {terms?.budget_eur !== undefined && <Line label="Your budget" value={money(terms.budget_eur)} />}
                <Divider my={4} />
                <Line label={`Whole contract (${yearsValue} ${yearsValue === 1 ? 'year' : 'years'} of wages)`} value={money(wageEur * 52 * yearsValue)} />
              </Stack>
              {over && (
                <Alert color="red" mt="xs" p="xs">
                  This is over your budget.
                </Alert>
              )}
            </Card>
          </>
        )}

        {!free && (rounds.length > 0 || talks) && (
          <Card withBorder padding="sm">
            <Group justify="space-between" mb="xs">
              <Text fw={600}>Negotiation</Text>
              <Group gap="xs">
                {isFinal && !ended && <Badge color="orange">Final price</Badge>}
                {ended && <Badge color="red">Talks ended</Badge>}
                <Dots left={ended ? 0 : roundsLeft} max={maxRounds} />
              </Group>
            </Group>
            <Timeline active={rounds.length + (talks ? 1 : 0)} bulletSize={14} lineWidth={2}>
              {talks && (
                <Timeline.Item title="Earlier talks">
                  <Text size="sm" c="dimmed">
                    Your last bid {money(talks.your_last_bid_eur)}; their price {money(talks.their_price_eur)} after {talks.rounds_used}{' '}
                    {talks.rounds_used === 1 ? 'round' : 'rounds'}.
                  </Text>
                </Timeline.Item>
              )}
              {rounds.map((r, i) => (
                <Timeline.Item key={i} title={`You bid ${money(r.bid)}`} color={answerColor(r.result)}>
                  <Text size="sm">
                    {r.result.message}
                    {r.result.status !== 'accepted' && r.result.fee_eur > 0 && ` Their price: ${money(r.result.fee_eur)}.`}
                  </Text>
                </Timeline.Item>
              ))}
            </Timeline>
          </Card>
        )}

        {free && last && !accepted && (
          <Alert color={answerColor(last)} title="No deal">
            {last.message}
            {last.status === 'rejected' && last.wage_eur > 0 && ` He asks ${wage(last.wage_eur)}.`}
          </Alert>
        )}
        {error && <Alert color="red">{error}</Alert>}

        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            {accepted ? 'Close' : 'Cancel'}
          </Button>
          {!accepted && (
            <>
              {!free && theirPrice !== null && (
                <Button variant="light" disabled={disabled} loading={offer.isPending} onClick={() => send(theirPrice)}>
                  Offer their price ({money(theirPrice)})
                </Button>
              )}
              <Button disabled={disabled} loading={offer.isPending} onClick={() => send(feeEur)}>
                {free ? 'Offer a contract' : 'Make offer'}
              </Button>
            </>
          )}
        </Group>
      </Stack>
    </Modal>
  )
}
