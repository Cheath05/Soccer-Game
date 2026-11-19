import { Alert, Card, SegmentedControl, Select, Stack, Text, Title } from '@mantine/core'

import { ApiError } from '../api/client'
import { useOfferRules, useSetOfferRules } from '../api/hooks'
import type { OfferMode } from '../api/types'

const MODES: { value: OfferMode; label: string; hint: string }[] = [
  { value: 'stop', label: 'Stop the game', hint: 'Continue and Sim to stop on the day a bid or loan request arrives, so you can answer it.' },
  { value: 'wait', label: 'Let them wait', hint: 'Bids don’t stop the game. They wait under Transfers, in Offers for your players, until they expire (a few days).' },
  { value: 'auto', label: 'Answer for me', hint: 'Bids are answered as they arrive, by your asking prices: at or above the price, he’s sold; below it, the club is asked for the price and either pays it or walks away. The news says what happened.' },
]

const DEFAULTS = [
  { value: 'none', label: 'Not for sale: turn bids down' },
  { value: '100', label: 'Sell at his value' },
  { value: '125', label: 'Sell at 125% of his value' },
  { value: '150', label: 'Sell at 150% of his value' },
  { value: '200', label: 'Sell at twice his value' },
  { value: '300', label: 'Sell at three times his value' },
]

/** Settings → Transfer offers: what bids for your players do while the game moves on. */
export default function OfferRulesCard() {
  const rules = useOfferRules()
  const save = useSetOfferRules()
  const data = rules.data
  if (!data) return rules.error ? <Text c="red">{rules.error.message}</Text> : null
  const update = (patch: Partial<{ mode: string; value_pct: number | null; loans: string }>) =>
    save.mutate({ mode: data.mode, value_pct: data.value_pct, loans: data.loans, ...patch })
  const priced = Object.keys(data.asking_prices).length
  const pct = data.value_pct === null ? 'none' : String(data.value_pct)
  return (
    <Card withBorder padding="md" aria-label="Transfer offers">
      <Title order={4} mb={4}>
        Transfer offers
      </Title>
      <Text size="sm" c="dimmed" mb="sm">
        What happens when a club bids for one of your players, or asks to borrow one, while the game moves on.
      </Text>
      <Stack gap="sm">
        <SegmentedControl
          value={data.mode}
          disabled={save.isPending}
          onChange={(v) => update({ mode: v })}
          data={MODES.map((m) => ({ value: m.value, label: m.label }))}
        />
        <Text size="sm">{MODES.find((m) => m.value === data.mode)?.hint}</Text>
        {data.mode === 'auto' && (
          <>
            <Text size="sm">
              {priced === 0
                ? 'You haven’t set an asking price for anyone yet: set one on a player’s page, under Up for sale.'
                : `${priced} of your players ${priced === 1 ? 'has' : 'have'} an asking price (on their pages, under Up for sale).`}
            </Text>
            <Select
              label="Players without an asking price"
              value={DEFAULTS.some((d) => d.value === pct) ? pct : null}
              placeholder={`Sell at ${data.value_pct}% of his value`}
              allowDeselect={false}
              disabled={save.isPending}
              onChange={(v) => v && update({ value_pct: v === 'none' ? null : Number(v) })}
              data={DEFAULTS}
            />
            <Select
              label="Loan requests"
              value={data.loans}
              allowDeselect={false}
              disabled={save.isPending}
              onChange={(v) => v && update({ loans: v })}
              data={[
                { value: 'reject', label: 'Turn them down' },
                { value: 'accept', label: 'Agree to them' },
              ]}
            />
          </>
        )}
        {save.error && (
          <Alert color="red" variant="light">
            {save.error instanceof ApiError ? save.error.message : 'The setting couldn’t be saved.'}
          </Alert>
        )}
      </Stack>
    </Card>
  )
}
