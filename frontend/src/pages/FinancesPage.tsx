import { Badge, Card, Grid, Group, Progress, SegmentedControl, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core'

import { useFinances } from '../api/hooks'
import type { FinanceLine } from '../api/types'
import { CURRENCIES, type Currency, confidenceColor, money, setCurrency, shortDate, useCurrency, wage } from '../lib/format'

function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`
}

function Figure({ label, value, note, color }: { label: string; value: string; note?: string; color?: string }) {
  return (
    <Card withBorder padding="sm">
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text fw={700} size="xl" c={color}>
        {value}
      </Text>
      {note && (
        <Text size="xs" c="dimmed">
          {note}
        </Text>
      )}
    </Card>
  )
}

function Lines({ title, lines, empty }: { title: string; lines: FinanceLine[]; empty: string }) {
  const total = lines.reduce((sum, l) => sum + l.amount_eur, 0)
  return (
    <Card withBorder h="100%">
      <Group justify="space-between">
        <Text fw={600}>{title}</Text>
        <Text fw={700} c={total < 0 ? 'red.7' : 'green.7'}>
          {money(total)}
        </Text>
      </Group>
      <Stack gap={4} mt="xs">
        {lines.length === 0 && (
          <Text size="sm" c="dimmed">
            {empty}
          </Text>
        )}
        {lines.map((l) => (
          <Group key={l.kind} justify="space-between">
            <Text size="sm">{l.label}</Text>
            <Text size="sm">{money(l.amount_eur)}</Text>
          </Group>
        ))}
      </Stack>
    </Card>
  )
}

export default function FinancesPage() {
  const currency = useCurrency()
  const { data: f, error } = useFinances()
  if (error) return <Text c="dimmed">No finances to show: {error.message}</Text>
  if (!f) return null
  const wageRoom = f.wage_budget_weekly_eur - f.wage_bill_weekly_eur
  const used = f.wage_budget_weekly_eur > 0 ? Math.min(100, (100 * f.wage_bill_weekly_eur) / f.wage_budget_weekly_eur) : 0
  const board = f.board

  return (
    <Stack>
      <Group justify="space-between" align="end">
        <div>
          <Title order={2}>Finances</Title>
          <Text c="dimmed">
            {f.club.name} · {f.season}
            {f.league ? ` · ${f.league}` : ''}
          </Text>
        </div>
        <Group gap="xs">
          <Text size="sm" c="dimmed">
            Show money in
          </Text>
          <SegmentedControl
            size="xs"
            value={currency}
            onChange={(v) => setCurrency(v as Currency)}
            data={(Object.keys(CURRENCIES) as Currency[]).map((c) => ({ value: c, label: CURRENCIES[c].label }))}
          />
        </Group>
      </Group>

      <SimpleGrid cols={{ base: 2, sm: 4 }}>
        <Figure label="Bank balance" value={money(f.balance_eur)} color={f.balance_eur < 0 ? 'red.7' : undefined} note={f.balance_eur < 0 ? 'In debt: no transfer budget' : undefined} />
        <Figure label="Transfer budget" value={money(f.transfer_budget_eur)} note="Set by the board each season" />
        <Figure label="Wage budget" value={wage(f.wage_budget_weekly_eur)} note={wageRoom >= 0 ? `${wage(wageRoom)} room` : `${wage(-wageRoom)} over`} />
        <Figure label="Expected revenue" value={money(f.projected_revenue_eur)} note="This season, mid-table" />
      </SimpleGrid>

      <Card withBorder>
        <Group justify="space-between" mb={6}>
          <Text size="sm">
            Wage bill {wage(f.wage_bill_weekly_eur)} of {wage(f.wage_budget_weekly_eur)}
          </Text>
          <Text size="sm" c="dimmed">
            {used.toFixed(0)}% of the wage budget
          </Text>
        </Group>
        <Progress value={used} color={used > 95 ? 'red' : used > 85 ? 'orange' : 'teal'} />
      </Card>

      <Grid>
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Card withBorder h="100%">
            <Text fw={600}>The board</Text>
            <Group mt="xs" gap="xs">
              <Badge size="lg" color={confidenceColor(board.confidence)}>
                {board.mood}
              </Badge>
              {board.confidence !== null && <Text size="sm">Confidence {board.confidence}/100</Text>}
            </Group>
            {board.confidence !== null && <Progress mt="sm" value={board.confidence} color={confidenceColor(board.confidence)} />}
            <Stack gap={2} mt="sm">
              {board.target !== null && (
                <Text size="sm">
                  Expects a {ordinal(board.target)}-place finish{board.league_size ? ` of ${board.league_size}` : ''}
                </Text>
              )}
              <Text size="sm" c="dimmed">
                {board.position !== null ? `Now ${ordinal(board.position)} after ${board.played} ${board.played === 1 ? 'game' : 'games'}` : 'The season hasn’t started'}
              </Text>
            </Stack>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
          <Lines title="Income this season" lines={f.income} empty="Nothing yet: money comes in on the 1st of each month." />
        </Grid.Col>
        <Grid.Col span={{ base: 12, sm: 6, md: 4 }}>
          <Lines title="Spending this season" lines={f.expenses} empty="Nothing yet: wages are paid on the 1st of each month." />
        </Grid.Col>
      </Grid>

      <Card withBorder>
        <Group justify="space-between">
          <Text fw={600}>Recent transactions</Text>
          <Text size="sm" c={f.net_eur < 0 ? 'red.7' : 'green.7'}>
            Net this season {money(f.net_eur)}
          </Text>
        </Group>
        <Table mt="xs" verticalSpacing={4}>
          <Table.Tbody>
            {f.recent.map((r, i) => (
              <Table.Tr key={`${r.date}-${r.kind}-${i}`}>
                <Table.Td w={90} c="dimmed">
                  {shortDate(r.date)}
                </Table.Td>
                <Table.Td>{r.label}</Table.Td>
                <Table.Td ta="right" c={r.amount_eur < 0 ? 'red.7' : 'green.7'}>
                  {money(r.amount_eur)}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Card>
    </Stack>
  )
}
