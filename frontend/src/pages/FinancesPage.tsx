import { Alert, Badge, Card, Divider, Grid, Group, Progress, SegmentedControl, SimpleGrid, Stack, Switch, Table, Text, Title } from '@mantine/core'

import PlayerLink from '../components/PlayerLink'
import { useChooseCurrency, useFinances, useSetBoard } from '../api/hooks'
import type { Board } from '../api/types'
import { CURRENCIES, type Currency, confidenceColor, money, monthYear, ordinal, shortDate, useCurrency, wage } from '../lib/format'

function Figure({ label, value, note, color }: { label: string; value: string; note?: string; color?: string }) {
  return (
    <Card withBorder padding="sm" h="100%">
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

/** One part of the month: income is green-neutral, a cost carries its minus sign. */
function Part({ label, eur }: { label: string; eur: number }) {
  return (
    <Group justify="space-between">
      <Text size="sm">{label}</Text>
      <Text size="sm">{money(eur)}</Text>
    </Group>
  )
}

function BoardCard({ board }: { board: Board }) {
  return (
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
  )
}

export default function FinancesPage() {
  const currency = useCurrency()
  const chooseCurrency = useChooseCurrency()
  const { data: f, error } = useFinances()
  const setBoard = useSetBoard()
  if (error) return <Text c="dimmed">No finances to show: {error.message}</Text>
  if (!f) return null
  const month = f.monthly
  const over = f.wage_bill_weekly_eur - f.wage_capacity_weekly_eur
  const used = f.wage_capacity_weekly_eur > 0 ? Math.min(100, (100 * f.wage_bill_weekly_eur) / f.wage_capacity_weekly_eur) : 100

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
            onChange={(v) => chooseCurrency(v as Currency)}
            data={(Object.keys(CURRENCIES) as Currency[]).map((c) => ({ value: c, label: CURRENCIES[c].label }))}
          />
        </Group>
      </Group>

      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        <Figure label="Balance" value={money(f.balance_eur)} color={f.balance_eur < 0 ? 'red.7' : undefined} note={f.balance_eur < 0 ? 'In debt: no budget at the next season’s start' : 'The club’s cash'} />
        <Figure label="Budget" value={money(f.budget_eur)} note="For transfer fees and new wages this season" />
        <Card withBorder padding="sm" h="100%">
          <Text size="xs" c="dimmed">
            Wages
          </Text>
          <Text fw={700} size="xl">
            {wage(f.wage_bill_weekly_eur)}
          </Text>
          {f.board_enabled ? (
            <>
              <Progress mt={6} value={used} color={over > 0 ? 'red' : used > 95 ? 'orange' : 'teal'} />
              <Text size="xs" c={over > 0 ? 'red.7' : 'dimmed'} mt={4}>
                {over > 0
                  ? `${wage(over)} more than your income supports (${wage(f.wage_capacity_weekly_eur)}): the board takes that off next season’s budget`
                  : `Your income supports ${wage(f.wage_capacity_weekly_eur)}`}
              </Text>
            </>
          ) : (
            <Text size="xs" c="dimmed" mt={4}>
              Paid from your budget: no wage limit without a board
            </Text>
          )}
          <Text size="xs" c="dimmed">
            Your budget could pay {wage(f.wage_room_weekly_eur)} more for the rest of the season
          </Text>
        </Card>
      </SimpleGrid>

      <Grid>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Card withBorder h="100%">
            <Text fw={600}>Each month</Text>
            <Text size="xs" c="dimmed">
              At today’s rates
            </Text>
            <Stack gap={4} mt="xs">
              <Part label="League TV money" eur={month.tv_eur} />
              <Part label="Commercial and matchday" eur={month.commercial_eur} />
              <Part label="Wages" eur={month.wages_eur} />
              <Part label="Running costs" eur={month.running_eur} />
              <Divider my={2} />
              <Group justify="space-between">
                <Text fw={600}>Profit</Text>
                <Text fw={700} c={month.profit_eur < 0 ? 'red.7' : 'green.7'}>
                  {money(month.profit_eur)}
                </Text>
              </Group>
            </Stack>
            <Text size="xs" c="dimmed" mt="sm">
              Profit so far this season: {money(f.season_profit_so_far_eur)}. It reaches your balance on the 1st of each month, and your budget at the start of the next season.
            </Text>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 6 }}>
          <Card withBorder h="100%">
            <Text fw={600}>Changes</Text>
            <Stack gap={4} mt="xs">
              {f.changes.length === 0 && (
                <Text size="sm" c="dimmed">
                  Nothing yet. A move up or down a division, or a new wage bill, shows here once.
                </Text>
              )}
              {f.changes.map((c) => (
                <Group key={`${c.date}-${c.label}`} justify="space-between" wrap="nowrap" align="start">
                  <Text size="sm">
                    <Text span c="dimmed">
                      {monthYear(c.date)}:
                    </Text>{' '}
                    {c.label} {money(Math.abs(c.before_eur))} → {money(Math.abs(c.after_eur))} a month
                  </Text>
                  <Text size="sm" fw={600} c={c.after_eur < c.before_eur ? 'red.7' : 'green.7'}>
                    {c.after_eur < c.before_eur ? '▼' : '▲'}
                  </Text>
                </Group>
              ))}
            </Stack>
          </Card>
        </Grid.Col>
      </Grid>

      <Card withBorder>
        <Text fw={600}>Transactions</Text>
        <Text size="xs" c="dimmed">
          One-off money: transfers, prize money and the like
        </Text>
        <Table mt="xs" verticalSpacing={4}>
          <Table.Tbody>
            {f.transactions.map((t, i) => (
              <Table.Tr key={`${t.date}-${t.kind}-${i}`}>
                <Table.Td w={90} c="dimmed">
                  {shortDate(t.date)}
                </Table.Td>
                <Table.Td>{t.player ? <PlayerLink player={t.player} label={t.label} /> : t.label}</Table.Td>
                <Table.Td ta="right" c={t.amount_eur < 0 ? 'red.7' : 'green.7'}>
                  {money(t.amount_eur)}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Card>

      <Grid>
        {f.board && (
          <Grid.Col span={{ base: 12, md: 6 }}>
            <BoardCard board={f.board} />
          </Grid.Col>
        )}
        <Grid.Col span={{ base: 12, md: f.board ? 6 : 12 }}>
          <Card withBorder h="100%">
            <Switch
              label="Board expectations"
              description="Off means no targets and no sacking, and your budget is all your cash."
              checked={f.board_enabled}
              disabled={setBoard.isPending}
              onChange={(e) => setBoard.mutate(e.currentTarget.checked)}
            />
            {setBoard.error && (
              <Alert color="red" mt="sm">
                {setBoard.error.message}
              </Alert>
            )}
          </Card>
        </Grid.Col>
      </Grid>
    </Stack>
  )
}
