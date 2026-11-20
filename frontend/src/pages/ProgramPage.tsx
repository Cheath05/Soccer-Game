import { Alert, Badge, Button, Card, Group, Loader, NumberInput, Progress, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core'
import { Link } from '@tanstack/react-router'
import { useState } from 'react'

import { useCareer } from '../api/hooks'
import { type Program, type ProgramFacility, useProgram, useSetClassBudget, useTurnOnBuilder, useUpgrade } from '../api/program'
import { longDate, money, shortDate } from '../lib/format'

// A college coach's program in the program builder mode (W9d; api/program.ts,
// world/college/program.py): the money, next season's class budget, the training facilities and
// the stadium, and the crowds at home games.

const LINE_LABEL: Record<string, string> = {
  allocation: 'Athletic department',
  tickets: 'Ticket sales',
  boosters: 'Boosters (regular season)',
  boosters_ncaa: 'Boosters (NCAA tournament)',
  ncaa: 'NCAA tournament',
  scholarships: 'Scholarships',
  staff: 'Coaching staff',
  upkeep: 'Facility upkeep',
  travel: 'Travel',
  build: 'Building work',
}

const FACILITY: Record<string, { title: string; about: string }> = {
  training: { title: 'Training facilities', about: 'Your players’ overall grows faster towards their potential. Recruits like them too.' },
  stadium: { title: 'Stadium', about: 'More seats sell more tickets, and a bigger, fuller crowd puts more pressure on visiting teams. Recruits like it too.' },
}

export default function ProgramPage() {
  const career = useCareer().data
  const program = useProgram(!!career?.college)
  if (career && !career.college) return <Alert>The program is for a college coach.</Alert>
  if (program.isPending) return <Loader />
  if (program.error) return <Alert color="red">{program.error.message}</Alert>
  const p = program.data
  if (p.mode !== 'builder') return <TurnOn />

  return (
    <Stack gap="sm">
      <Title order={2}>Program</Title>
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="sm">
        <Money p={p} />
        <ClassBudget p={p} />
      </SimpleGrid>
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="sm">
        {p.facilities.map((f) => (
          <FacilityCard key={f.kind} f={f} p={p} />
        ))}
      </SimpleGrid>
      <Crowds p={p} />
    </Stack>
  )
}

function TurnOn() {
  const turnOn = useTurnOnBuilder()
  return (
    <Stack gap="sm" maw={620}>
      <Title order={2}>Program</Title>
      <Text>
        Your career plays the classic college game. The program builder gives every program money (the athletic department’s allocation, ticket sales, boosters and NCAA tournament payouts) to spend on scholarships, training facilities and the stadium, and the other programs build too.
      </Text>
      <Text size="sm" c="dimmed">
        It can’t be turned off again.
      </Text>
      {turnOn.error && <Alert color="red">{turnOn.error.message}</Alert>}
      <Group>
        <Button loading={turnOn.isPending} onClick={() => turnOn.mutate()}>
          Turn on the program builder
        </Button>
      </Group>
    </Stack>
  )
}

function Money({ p }: { p: Program }) {
  const income = p.season.filter((l) => l.amount_eur > 0)
  const costs = p.season.filter((l) => l.amount_eur < 0)
  const net = p.season.reduce((sum, l) => sum + l.amount_eur, 0)
  return (
    <Card withBorder padding="md">
      <Group justify="space-between" align="baseline">
        <span className="fs-label">Balance</span>
        <Text size="xs" c="dimmed">
          Next season’s allocation {money(p.next_allocation_eur)}
        </Text>
      </Group>
      <Text className="fs-num" fz={32} c={p.balance_eur < 0 ? 'red.5' : undefined}>
        {money(p.balance_eur)}
      </Text>
      <Table mt="xs" verticalSpacing={4} withRowBorders={false}>
        <Table.Tbody>
          {[...income, ...costs].map((l) => (
            <Table.Tr key={l.kind}>
              <Table.Td>
                <Text size="sm">{LINE_LABEL[l.kind] ?? l.kind}</Text>
              </Table.Td>
              <Table.Td ta="right">
                <Text size="sm" c={l.amount_eur < 0 ? 'red.5' : 'teal'}>
                  {money(l.amount_eur)}
                </Text>
              </Table.Td>
            </Table.Tr>
          ))}
          <Table.Tr>
            <Table.Td>
              <Text size="sm" fw={700}>
                This season so far
              </Text>
            </Table.Td>
            <Table.Td ta="right">
              <Text size="sm" fw={700} c={net < 0 ? 'red.5' : 'teal'}>
                {money(net)}
              </Text>
            </Table.Td>
          </Table.Tr>
        </Table.Tbody>
      </Table>
    </Card>
  )
}

function ClassBudget({ p }: { p: Program }) {
  const setBudget = useSetClassBudget()
  const [value, setValue] = useState<number>(p.class_budget)
  return (
    <Card withBorder padding="md">
      <span className="fs-label">Scholarships for next season’s class</span>
      <Group align="flex-end" gap="sm" mt={4}>
        <NumberInput
          w={130}
          min={0}
          max={40}
          step={0.5}
          decimalScale={2}
          value={value}
          onChange={(v) => setValue(Number(v) || 0)}
          suffix=" full"
          aria-label="Class budget in full scholarships"
        />
        <Button loading={setBudget.isPending} disabled={value === p.class_budget} onClick={() => setBudget.mutate(value)}>
          Set
        </Button>
      </Group>
      <Text size="sm" mt="xs">
        {p.class_budget.toFixed(2)} full scholarships set aside, {p.class_committed.toFixed(2)} committed. A full one costs {money(p.scholarship_eur)} a year, paid from each season’s start.
      </Text>
      <Text size="xs" c="dimmed" mt={4}>
        You can afford up to {p.class_affordable.toFixed(2)} after next season’s staff, upkeep and returning players. Recruiting offers come out of this.
      </Text>
      <Progress mt={6} size={4} value={p.class_budget ? (100 * p.class_committed) / p.class_budget : 0} aria-label="Class budget used" />
      {setBudget.error && (
        <Alert mt="xs" color="red">
          {setBudget.error.message}
        </Alert>
      )}
      <Text size="xs" mt={6}>
        <Link to="/recruiting">Go to Recruiting</Link>
      </Text>
    </Card>
  )
}

function FacilityCard({ f, p }: { f: ProgramFacility; p: Program }) {
  const upgrade = useUpgrade()
  const info = FACILITY[f.kind]
  const building = f.building_to !== null
  const canPay = f.next_cost_eur !== null && p.balance_eur >= f.next_cost_eur
  return (
    <Card withBorder padding="md">
      <Group justify="space-between" align="center">
        <Text fw={700}>{info.title}</Text>
        <Badge variant="light">Level {f.level} of 5</Badge>
      </Group>
      <Text size="sm" mt={4}>
        {f.effect}
      </Text>
      <Text size="xs" c="dimmed">
        {info.about} Upkeep {money(f.upkeep_eur)} a season.
      </Text>
      <Progress mt="xs" size={6} value={f.level * 20} aria-label={`Level ${f.level} of 5`} />
      {building ? (
        <Alert mt="sm" color="teal" variant="light">
          Level {f.building_to} is being built: ready for {f.ready_season}.
        </Alert>
      ) : f.next_cost_eur === null ? (
        <Text size="sm" mt="sm" c="teal">
          At the top level.
        </Text>
      ) : (
        <Stack gap={4} mt="sm">
          <Text size="sm">
            Level {f.level + 1}: {f.next_effect}
          </Text>
          <Group gap="xs">
            <Button size="xs" disabled={!canPay} loading={upgrade.isPending} onClick={() => upgrade.mutate(f.kind)}>
              Build it for {money(f.next_cost_eur)}
            </Button>
            {!canPay && (
              <Text size="xs" c="dimmed">
                Not enough money yet
              </Text>
            )}
          </Group>
          <Text size="xs" c="dimmed">
            Ordered before {longDate(p.build_cutoff)}, it’s ready next season; later, the season after.
          </Text>
        </Stack>
      )}
      {upgrade.error && (
        <Alert mt="xs" color="red">
          {upgrade.error.message}
        </Alert>
      )}
    </Card>
  )
}

function Crowds({ p }: { p: Program }) {
  if (!p.crowds.length)
    return (
      <Text size="sm" c="dimmed">
        No home games yet this season. Your stadium holds {p.capacity.toLocaleString()}.
      </Text>
    )
  return (
    <Card withBorder padding="md">
      <Group justify="space-between">
        <span className="fs-label">Home crowds</span>
        <Text size="xs" c="dimmed">
          Capacity {p.capacity.toLocaleString()}
        </Text>
      </Group>
      <Table mt="xs" verticalSpacing={4}>
        <Table.Tbody>
          {p.crowds.map((c) => (
            <Table.Tr key={c.fixture_id}>
              <Table.Td w={90}>
                <Text size="sm" c="dimmed">
                  {shortDate(c.date)}
                </Text>
              </Table.Td>
              <Table.Td>
                <Link to="/match/$fixtureId" params={{ fixtureId: String(c.fixture_id) }}>
                  <Text size="sm" span>
                    v {c.opponent}
                  </Text>
                </Link>
              </Table.Td>
              <Table.Td ta="right">
                <Text size="sm">{c.attendance.toLocaleString()}</Text>
              </Table.Td>
              <Table.Td w={120} visibleFrom="sm">
                <Progress value={(100 * c.attendance) / Math.max(1, p.capacity)} size="sm" aria-label="How full" />
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Card>
  )
}
