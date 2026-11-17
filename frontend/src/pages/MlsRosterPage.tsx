import { Alert, Badge, Button, Card, Group, List, Loader, Modal, NativeSelect, Progress, SegmentedControl, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'
import { type ReactNode, useState } from 'react'

import { type Designation, type MlsPlayer, type MlsRoster, useBuySlot, useMlsRoster, useSetDesignation, useSetRosterModel, useSlotSellers } from '../api/americas'
import { ApiError } from '../api/client'
import BackButton from '../components/BackButton'
import PlayerLink from '../components/PlayerLink'
import { money, positionColor, ratingColor } from '../lib/format'
import { useDevice } from '../lib/device'

// MLS's roster rules for the user's club (api/mls.py; docs/plans/w9a-mls-rules-notes.md): the
// salary budget after allocation money, each player's designation and budget charge, the slots,
// the roster model, and what keeps the club from complying.

const DESIGNATIONS: Record<Designation, { short: string; label: string; color: string }> = {
  dp: { short: 'DP', label: 'Designated Player', color: 'yellow' },
  u22: { short: 'U22', label: 'U22 Initiative', color: 'grape' },
  senior: { short: 'Senior', label: 'Senior', color: 'blue' },
  supplemental: { short: 'Supp', label: 'Supplemental', color: 'gray' },
  homegrown: { short: 'HG', label: 'Homegrown', color: 'green' },
  generation_adidas: { short: 'GA', label: 'Generation adidas', color: 'cyan' },
}

/** A "designation:roster" choice as the select shows it. */
function optionLabel(option: string, p: MlsPlayer, maxCharge: number): string {
  const [designation, roster] = option.split(':') as [Designation, string]
  if (designation === 'homegrown') return `Homegrown (${roster})`
  if (designation === 'senior' && p.salary_eur > maxCharge) return 'Senior (TAM/GAM buy-down)'
  return DESIGNATIONS[designation]?.label ?? designation
}

export default function MlsRosterPage() {
  const { phone } = useDevice()
  const roster = useMlsRoster()
  const navigate = useNavigate()
  const setDesignation = useSetDesignation()
  const setModel = useSetRosterModel()
  // A refusal belongs to the player (or the control) it was for.
  const [refusal, setRefusal] = useState<{ key: string; text: string } | null>(null)
  const [buying, setBuying] = useState(false)

  if (roster.isPending) return <Loader />
  if (!roster.data) {
    const notMls = roster.error instanceof ApiError && roster.error.status === 404
    return (
      <Stack>
        <Title order={2}>MLS roster</Title>
        <Text c={notMls ? 'dimmed' : 'red'}>{notMls ? 'Your club doesn’t play under MLS’s roster rules.' : roster.error?.message}</Text>
      </Stack>
    )
  }
  const r = roster.data
  const yours = r.yours

  const onDesignate = (p: MlsPlayer, option: string) => {
    const [designation, slot] = option.split(':') as [Designation, string]
    setRefusal(null)
    setDesignation.mutate(
      { player_id: p.id, designation, roster: slot },
      { onError: (e) => setRefusal({ key: `p${p.id}`, text: e.message }) },
    )
  }
  const onModel = (model: string) => {
    setRefusal(null)
    setModel.mutate({ model: Number(model) }, { onError: (e) => setRefusal({ key: 'model', text: e.message }) })
  }

  const senior = r.players.filter((p) => p.roster === 'senior')
  const supplemental = r.players.filter((p) => p.roster === 'supplemental')
  const usedShare = r.budget_eur > 0 ? Math.min(100, (r.budget_used_eur / r.budget_eur) * 100) : 0
  const over = r.budget_left_eur < 0
  const busyId = setDesignation.isPending ? setDesignation.variables?.player_id : undefined

  return (
    <Stack gap="sm">
      <Group justify="space-between" align="center" wrap="nowrap">
        <div style={{ minWidth: 0 }}>
          <Title order={2}>MLS roster</Title>
          <Text size="sm" c="dimmed" truncate>
            {r.club.name} · Roster Model {r.roster_model}
          </Text>
        </div>
        <Group gap="xs" wrap="nowrap" style={{ flexShrink: 0 }}>
          <Badge size="lg" variant="light" color={r.compliant ? 'teal' : 'red'}>
            {r.compliant ? 'Compliant' : 'Not compliant'}
          </Badge>
          {!phone && <BackButton fallback="/squad" />}
        </Group>
      </Group>

      {!r.compliant && (
        <Alert color="red" variant="filled" title={r.adding_blocked ? 'Not compliant: you can’t sign or borrow anyone until this is fixed' : 'Not compliant with MLS’s rules'}>
          <List size="sm" spacing={2} c="white">
            {r.problems.map((text) => (
              <List.Item key={text}>{text}</List.Item>
            ))}
          </List>
          <Text size="xs" mt={6} c="white" opacity={0.85}>
            Matches are never blocked. Change designations below, sell or release a player, or buy an international slot.
          </Text>
        </Alert>
      )}

      <Card className="fs-hero" padding="lg">
        <Group justify="space-between" align="flex-end" wrap="nowrap">
          <div>
            <span className="fs-label">Salary budget left</span>
            <Text className="fs-num" fz={phone ? 34 : 40} lh={1.05} c={over ? 'red.5' : undefined}>
              {money(r.budget_left_eur)}
            </Text>
          </div>
          <Stack gap={0} align="flex-end">
            <span className="fs-label">Used</span>
            <Text className="fs-num" fz={20}>
              {money(r.budget_used_eur)} <Text span c="dimmed" fz={15}>of {money(r.budget_eur)}</Text>
            </Text>
          </Stack>
        </Group>
        <Progress mt="sm" size={8} value={usedShare} color={over ? 'red' : usedShare > 95 ? 'yellow' : 'teal'} aria-label="Salary budget used" />
        <Text size="xs" c="dimmed" mt={6}>
          Senior roster charges after TAM and GAM buy-downs. One player’s charge is at most {money(r.max_charge_eur)}.
          {r.empty_senior_slots_charged > 0 && ` ${r.empty_senior_slots_charged} empty senior ${r.empty_senior_slots_charged === 1 ? 'slot is' : 'slots are'} charged the minimum.`}
        </Text>
      </Card>

      <SimpleGrid cols={{ base: 2, md: 4 }} spacing="sm">
        <Money label="TAM left" value={r.allocation.tam_left_eur} note={`${money(r.allocation.tam_used_eur)} used of ${money(r.allocation.tam_eur)}`} />
        <Money
          label="GAM left"
          value={r.allocation.gam_left_eur}
          note={`${money(r.allocation.gam_used_eur)} used of ${money(r.allocation.gam_eur)}${r.allocation.gam_expiring_eur > 0 ? ` · ${money(r.allocation.gam_expiring_eur)} expires this season` : ''}`}
        />
        <Slots label="Designated Players" used={r.slots.designated_players} of={r.slots.designated_slots} />
        <Slots label="U22 Initiative" used={r.slots.u22} of={r.slots.u22_slots} />
        <Slots
          label="International slots"
          used={r.slots.internationals}
          of={r.slots.international_slots}
          action={yours ? (
            <Button size="compact-xs" variant="light" onClick={() => setBuying(true)}>
              Buy a slot
            </Button>
          ) : undefined}
        />
        <Slots label="Senior roster" used={r.slots.senior} of={r.slots.senior_slots} />
        <Slots label="Supplemental" used={r.slots.supplemental} of={r.slots.supplemental_slots} />
        <ModelCard roster={r} disabled={!yours || !r.model_choosable || setModel.isPending} onChange={onModel} />
      </SimpleGrid>
      {refusal?.key === 'model' && <Refusal text={refusal.text} />}

      {[
        { title: 'Senior roster', note: 'Slots 1–20, charged against the budget', list: senior },
        { title: 'Supplemental roster', note: 'Slots 21–30, not charged', list: supplemental },
      ].map((section) => (
        <Stack key={section.title} gap={6}>
          <Group justify="space-between" align="baseline" mt="xs">
            <Title order={3}>{section.title}</Title>
            <Text size="xs" c="dimmed">
              {section.note}
            </Text>
          </Group>
          {section.list.length === 0 && (
            <Text size="sm" c="dimmed">
              Nobody.
            </Text>
          )}
          {phone ? (
            <Stack gap={8}>
              {section.list.map((p) => (
                <Card key={p.id} withBorder padding="sm" className="fs-row">
                  <Group wrap="nowrap" gap="sm" align="flex-start" style={{ cursor: 'pointer' }} onClick={() => void navigate({ to: '/players/$playerId', params: { playerId: String(p.id) } })}>
                    <Badge color={positionColor(p.position)} variant="light" w={46} style={{ flexShrink: 0 }}>
                      {p.position}
                    </Badge>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <Group gap={6} wrap="nowrap">
                        <Text fw={600} truncate>
                          {p.name}
                        </Text>
                        <Flags p={p} />
                      </Group>
                      <Text size="xs" c="dimmed" truncate>
                        {p.age}y · paid {money(p.salary_eur)}/yr
                      </Text>
                      <Group gap={6} mt={4} wrap="wrap">
                        <DesignationBadge p={p} />
                        <ChargeText p={p} roster={p.roster} />
                      </Group>
                    </div>
                    <Text className="fs-num" fz={28} lh={1} c={ratingColor(p.overall)} style={{ flexShrink: 0 }}>
                      {p.overall}
                    </Text>
                  </Group>
                  {yours && p.options.length > 1 && (
                    <DesignationSelect p={p} maxCharge={r.max_charge_eur} busy={busyId === p.id} onChange={onDesignate} mt="xs" />
                  )}
                  {refusal?.key === `p${p.id}` && <Refusal text={refusal.text} />}
                </Card>
              ))}
            </Stack>
          ) : (
            section.list.length > 0 && (
              <Table.ScrollContainer minWidth={860}>
                <Table highlightOnHover striped verticalSpacing={6}>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th w={60}>Pos</Table.Th>
                      <Table.Th>Name</Table.Th>
                      <Table.Th ta="right">Age</Table.Th>
                      <Table.Th ta="right">Ovr</Table.Th>
                      <Table.Th ta="right">Salary/yr</Table.Th>
                      <Table.Th w={230}>Designation</Table.Th>
                      <Table.Th ta="right">Charge</Table.Th>
                      <Table.Th ta="right">Buy-down</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {section.list.map((p) => (
                      <PlayerRow
                        key={p.id}
                        p={p}
                        roster={r}
                        busy={busyId === p.id}
                        onDesignate={onDesignate}
                        refusal={refusal?.key === `p${p.id}` ? refusal.text : null}
                      />
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            )
          )}
        </Stack>
      ))}

      {yours && <SlotModal opened={buying} onClose={() => setBuying(false)} />}
    </Stack>
  )
}

function PlayerRow({ p, roster, busy, onDesignate, refusal }: {
  p: MlsPlayer
  roster: MlsRoster
  busy: boolean
  onDesignate: (p: MlsPlayer, option: string) => void
  refusal: string | null
}) {
  return (
    <>
      <Table.Tr>
        <Table.Td>
          <Badge color={positionColor(p.position)} variant="light" w={44}>
            {p.position}
          </Badge>
        </Table.Td>
        <Table.Td>
          <Group gap={6} wrap="nowrap">
            <Text size="sm" fw={500} component="span">
              <PlayerLink player={p} />
            </Text>
            <Flags p={p} />
          </Group>
        </Table.Td>
        <Table.Td ta="right">{p.age}</Table.Td>
        <Table.Td ta="right">
          <Text fw={700} size="sm" c={ratingColor(p.overall)} span>
            {p.overall}
          </Text>
        </Table.Td>
        <Table.Td ta="right">{money(p.salary_eur)}</Table.Td>
        <Table.Td>
          {roster.yours && p.options.length > 1 ? (
            <DesignationSelect p={p} maxCharge={roster.max_charge_eur} busy={busy} onChange={onDesignate} />
          ) : (
            <DesignationBadge p={p} />
          )}
        </Table.Td>
        <Table.Td ta="right">
          <Text size="sm" fw={600} span>
            {p.roster === 'senior' ? money(p.charge.charge_eur) : '–'}
          </Text>
        </Table.Td>
        <Table.Td ta="right">
          <BuyDown p={p} />
        </Table.Td>
      </Table.Tr>
      {refusal && (
        <Table.Tr>
          <Table.Td colSpan={8} pt={0}>
            <Refusal text={refusal} />
          </Table.Td>
        </Table.Tr>
      )}
    </>
  )
}

function DesignationSelect({ p, maxCharge, busy, onChange, mt }: {
  p: MlsPlayer
  maxCharge: number
  busy: boolean
  onChange: (p: MlsPlayer, option: string) => void
  mt?: string
}) {
  const current = `${p.designation}:${p.roster}`
  const options = p.options.includes(current) ? p.options : [current, ...p.options]
  return (
    <NativeSelect
      size="xs"
      mt={mt}
      aria-label={`Designation of ${p.name}`}
      value={current}
      disabled={busy}
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => onChange(p, e.currentTarget.value)}
      data={options.map((o) => ({ value: o, label: optionLabel(o, p, maxCharge) }))}
    />
  )
}

function DesignationBadge({ p }: { p: MlsPlayer }) {
  const d = DESIGNATIONS[p.designation]
  return (
    <Badge size="sm" variant="light" color={d?.color ?? 'gray'}>
      {d?.label ?? p.designation}
    </Badge>
  )
}

/** Where his charge comes from: the charge, and what TAM or GAM took off it. */
function ChargeText({ p, roster }: { p: MlsPlayer; roster: string }) {
  if (roster !== 'senior') return <Text size="xs" c="dimmed">Not charged</Text>
  return (
    <Text size="xs" c="dimmed">
      Charge <Text span fw={700} c="gray.2">{money(p.charge.charge_eur)}</Text>
      {p.charge.tam_eur > 0 && ` · TAM −${money(p.charge.tam_eur)}`}
      {p.charge.gam_eur > 0 && ` · GAM −${money(p.charge.gam_eur)}`}
    </Text>
  )
}

function BuyDown({ p }: { p: MlsPlayer }) {
  if (p.charge.tam_eur === 0 && p.charge.gam_eur === 0) return <Text size="sm" c="dimmed" span>–</Text>
  return (
    <Group gap={4} justify="flex-end" wrap="nowrap" component="span" display="inline-flex">
      {p.charge.tam_eur > 0 && (
        <Badge size="sm" variant="light" color="teal">
          TAM {money(p.charge.tam_eur)}
        </Badge>
      )}
      {p.charge.gam_eur > 0 && (
        <Badge size="sm" variant="light" color="orange">
          GAM {money(p.charge.gam_eur)}
        </Badge>
      )}
    </Group>
  )
}

function Flags({ p }: { p: MlsPlayer }) {
  return (
    <>
      {p.international && <Badge size="xs" variant="outline" color="gray" style={{ flexShrink: 0 }} title="Takes an international slot">INT</Badge>}
      {p.canadian && <Badge size="xs" variant="outline" color="red" style={{ flexShrink: 0 }} title="Canadian">CAN</Badge>}
      {p.loan === 'in' && <Badge size="xs" variant="light" color="blue" style={{ flexShrink: 0 }}>On loan</Badge>}
      {p.loan === 'out' && <Badge size="xs" variant="light" color="gray" style={{ flexShrink: 0 }}>Lent out</Badge>}
    </>
  )
}

function Refusal({ text }: { text: string }) {
  return (
    <Text size="xs" c="red.4" mt={6} role="alert">
      {text}
    </Text>
  )
}

function Money({ label, value, note }: { label: string; value: number; note: string }) {
  return (
    <Card withBorder padding="sm">
      <span className="fs-label">{label}</span>
      <Text className="fs-num" fz={24} lh={1.1} c={value < 0 ? 'red.5' : undefined}>
        {money(value)}
      </Text>
      <Text size="xs" c="dimmed">
        {note}
      </Text>
    </Card>
  )
}

function Slots({ label, used, of, action }: { label: string; used: number; of: number; action?: ReactNode }) {
  const full = used >= of
  return (
    <Card withBorder padding="sm">
      <Group justify="space-between" gap={4} wrap="nowrap">
        <span className="fs-label">{label}</span>
      </Group>
      <Group justify="space-between" align="center" wrap="nowrap" gap={4}>
        <Text className="fs-num" fz={24} lh={1.1} c={used > of ? 'red.5' : undefined}>
          {used}
          <Text span c="dimmed" fz={16}>
            {' '}/ {of}
          </Text>
        </Text>
        {action}
      </Group>
      <Text size="xs" c="dimmed">
        {used > of ? `${used - of} over` : full ? 'Full' : `${of - used} free`}
      </Text>
    </Card>
  )
}

function ModelCard({ roster, disabled, onChange }: { roster: MlsRoster; disabled: boolean; onChange: (model: string) => void }) {
  return (
    <Card withBorder padding="sm">
      <span className="fs-label">Roster model</span>
      <SegmentedControl
        mt={4}
        size="xs"
        fullWidth
        aria-label="Roster model"
        value={String(roster.roster_model)}
        onChange={onChange}
        disabled={disabled}
        data={[
          { value: '1', label: '1: 3 DP' },
          { value: '2', label: '2: 2 DP' },
        ]}
      />
      <Text size="xs" c="dimmed" mt={4}>
        {roster.roster_model === 1 ? '3 DPs, 3 U22 players' : '2 DPs, 4 U22 players, more GAM'}
        {roster.yours && !roster.model_choosable ? ' · fixed after the first league match' : ''}
      </Text>
    </Card>
  )
}

function SlotModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const sellers = useSlotSellers(opened)
  const buy = useBuySlot()
  const [error, setError] = useState<string | null>(null)
  const close = () => {
    setError(null)
    buy.reset()
    onClose()
  }
  const data = sellers.data
  return (
    <Modal opened={opened} onClose={close} title="Buy an international slot" centered>
      {sellers.isPending ? (
        <Loader />
      ) : !data ? (
        <Text c="red">{sellers.error?.message}</Text>
      ) : (
        <Stack gap="sm">
          <Text size="sm">
            A slot for this season costs {money(data.price_eur)} of GAM. You have {money(data.gam_left_eur)} of GAM free.
          </Text>
          {data.sellers.length === 0 && (
            <Text size="sm" c="dimmed">
              No MLS club has a slot to spare.
            </Text>
          )}
          {data.sellers.map((s) => (
            <Group key={s.club.id} justify="space-between" wrap="nowrap" className="fs-row" px={4} py={2}>
              <div style={{ minWidth: 0 }}>
                <Text size="sm" fw={600} truncate>
                  {s.club.name}
                </Text>
                <Text size="xs" c="dimmed">
                  {s.spare} to spare
                </Text>
              </div>
              <Button
                size="xs"
                variant="light"
                loading={buy.isPending && buy.variables?.from_club_id === s.club.id}
                disabled={buy.isPending}
                onClick={() => {
                  setError(null)
                  buy.mutate({ from_club_id: s.club.id }, { onSuccess: close, onError: (e) => setError(e.message) })
                }}
              >
                Buy
              </Button>
            </Group>
          ))}
          {error && <Refusal text={error} />}
        </Stack>
      )}
    </Modal>
  )
}
