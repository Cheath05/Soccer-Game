import { Alert, Badge, Button, Card, Drawer, Group, Loader, NumberInput, Pagination, Progress, SegmentedControl, Select, SimpleGrid, Slider, Stack, Switch, Table, Text, TextInput, Title, UnstyledButton } from '@mantine/core'
import { Link } from '@tanstack/react-router'
import { useState } from 'react'

import {
  type Priority,
  type Recruit,
  type RecruitFilters,
  type Recruiting,
  useClassRankings,
  useGodPlayer,
  useMakeOffer,
  usePullOffer,
  useRecruit,
  useRecruiting,
  useRecruits,
  useSetTarget,
  useSignGodPlayer,
} from '../api/recruiting'
import { useCareer } from '../api/hooks'
import ClubLink from '../components/ClubLink'
import { scholarshipLabel, stars } from '../lib/college'
import { useDevice } from '../lib/device'
import { longDate, positionColor } from '../lib/format'
import { useUrlState } from '../lib/urlState'

// High-school recruiting for a college coach (W9c; api/recruiting.ts, world/college/coach.py):
// the national class with your staff's estimates, your target list (the staff spread their
// week over it by priority), your scholarship offers, your class so far and the class rankings.

const PAGE = 50
const STATES = ['AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'DC', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY']
const POSITIONS = ['GK', 'DEF', 'CB', 'LB', 'RB', 'MID', 'DM', 'CM', 'AM', 'ATT', 'LW', 'RW', 'ST']
const PRIORITY_LABEL: Record<Priority, string> = { top: 'Top', high: 'High', watch: 'Watch' }
const PRIORITY_COLOR: Record<Priority, string> = { top: 'orange', high: 'teal', watch: 'gray' }

export default function RecruitingPage() {
  const { phone } = useDevice()
  const career = useCareer().data
  const summary = useRecruiting(!!career?.college)
  const [tab, setTab] = useUrlState('tab', 'board')
  const [open, setOpen] = useState<number | null>(null)

  if (career && !career.college) return <Alert>Recruiting is for a college coach: start a career at an NCAA program.</Alert>
  if (summary.isPending) return <Loader />
  if (summary.error) return <Alert color="red">{summary.error.message}</Alert>
  const s = summary.data
  const tabs = [
    { value: 'board', label: 'Board' },
    { value: 'targets', label: `My targets (${s.targets})` },
    { value: 'offers', label: `My offers (${s.open_offers})` },
    { value: 'class', label: `My class (${s.class_count})` },
    { value: 'rankings', label: 'Class rankings' },
  ]

  return (
    <Stack gap="sm">
      <Group justify="space-between" align="center">
        <div>
          <Title order={2}>Recruiting</Title>
          <Text size="sm" c="dimmed">
            The high-school class that joins next season
          </Text>
        </div>
        <PhaseBadge s={s} />
      </Group>
      <SummaryCards s={s} />
      <GodPlayerCard />
      {phone ? (
        <Select aria-label="Show" value={tab} onChange={(v) => v && setTab(v)} allowDeselect={false} data={tabs} />
      ) : (
        <SegmentedControl fullWidth value={tab} onChange={setTab} data={tabs} />
      )}
      {tab === 'rankings' ? <ClassRankings /> : <RecruitList key={tab} view={tab as RecruitFilters['view']} onOpen={setOpen} />}
      <RecruitCard id={open} summary={s} onClose={() => setOpen(null)} />
    </Stack>
  )
}

/** Once every few seasons: a freshman with a pro's ratings, at a random position. */
function GodPlayerCard() {
  const god = useGodPlayer()
  const sign = useSignGodPlayer()
  const [sure, setSure] = useState(false)
  if (!god.data) return null
  const g = god.data
  const latest = g.signed[0]
  return (
    <Card withBorder padding="sm" bg={g.available ? 'var(--mantine-color-yellow-light)' : undefined}>
      <Group justify="space-between" align="center" wrap="wrap" gap="xs">
        <div style={{ flex: 1, minWidth: 220 }}>
          <Text fw={700}>OP player</Text>
          <Text size="xs" c="dimmed">
            Once every {g.every_seasons} seasons: a freshman with a pro&apos;s ratings (about {g.overall} overall) at a random position, on no scholarship. He stays all four years.
          </Text>
          {latest && (
            <Text size="sm" mt={4}>
              Yours:{' '}
              <Link to="/players/$playerId" params={{ playerId: String(latest.id) }}>
                {latest.name}
              </Link>
              {g.next_season ? ` · the next one in ${g.next_season}` : ''}
            </Text>
          )}
        </div>
        {g.available &&
          (sure ? (
            <Group gap="xs">
              <Button color="yellow" loading={sign.isPending} onClick={() => sign.mutate(undefined, { onSettled: () => setSure(false) })}>
                Sign him
              </Button>
              <Button variant="default" onClick={() => setSure(false)}>
                Not yet
              </Button>
            </Group>
          ) : (
            <Button color="yellow" variant="light" onClick={() => setSure(true)}>
              Sign a OP player
            </Button>
          ))}
      </Group>
      {sure && (
        <Text size="xs" mt={6}>
          You get one now and the next in {g.every_seasons} seasons. His position is random.
        </Text>
      )}
      {sign.error && (
        <Alert mt="xs" color="red">
          {sign.error.message}
        </Alert>
      )}
    </Card>
  )
}

function PhaseBadge({ s }: { s: Recruiting }) {
  const text = {
    before: `Offers open ${longDate(s.start)}`,
    open: `Signing day ${longDate(s.signing_day)}`,
    late: `Late signings until ${longDate(s.close)}`,
    closed: 'The class has closed: it joins at the season’s start',
  }[s.phase]
  return (
    <Badge size="lg" variant="light" color={s.phase === 'open' ? 'teal' : s.phase === 'late' ? 'orange' : 'gray'} style={{ textTransform: 'none' }}>
      {text}
    </Badge>
  )
}

function SummaryCards({ s }: { s: Recruiting }) {
  const left = Math.max(0, s.funding - s.returning_money - s.class_money)
  const roster = s.returning + s.class_count
  return (
    <SimpleGrid cols={{ base: 2, md: 4 }} spacing="xs">
      <Card withBorder padding="sm">
        <span className="fs-label">Scholarships left</span>
        <Text className="fs-num" fz={24}>
          {left.toFixed(2)}
        </Text>
        <Text size="xs" c="dimmed">
          of {s.funding} full · {s.offered_money.toFixed(2)} on offer
        </Text>
        <Progress mt={6} size={4} value={(100 * (s.returning_money + s.class_money)) / s.funding} aria-label="Scholarship money used" />
      </Card>
      <Card withBorder padding="sm">
        <span className="fs-label">Next season’s roster</span>
        <Text className="fs-num" fz={24}>
          {roster} / {s.places}
        </Text>
        <Text size="xs" c="dimmed">
          {s.returning} returning · {s.class_count} signed or committed
        </Text>
        <Progress mt={6} size={4} value={(100 * roster) / s.places} aria-label="Roster places used" />
      </Card>
      <Card withBorder padding="sm">
        <span className="fs-label">Staff effort a week</span>
        <Text className="fs-num" fz={24}>
          {s.effort}
        </Text>
        <Text size="xs" c="dimmed">
          {s.targets ? `Per target: top ${s.per_target.top}, high ${s.per_target.high}, watch ${s.per_target.watch}` : 'Add targets to spend it'}
        </Text>
      </Card>
      <Card withBorder padding="sm">
        <span className="fs-label">Campus visits</span>
        <Text className="fs-num" fz={24}>
          {s.visits_used} / {s.visits}
        </Text>
        <Text size="xs" c="dimmed">
          Top targets with your offer visit when keen · prestige {s.prestige}
        </Text>
      </Card>
    </SimpleGrid>
  )
}

function RecruitList({ view, onOpen }: { view: RecruitFilters['view']; onOpen: (id: number) => void }) {
  const { phone } = useDevice()
  const [position, setPosition] = useUrlState<string | null>('pos', null)
  const [state, setState] = useUrlState<string | null>('state', null)
  const [starFilter, setStars] = useUrlState('stars', 'all')
  const [q, setQ] = useState('')
  const [openOnly, setOpenOnly] = useUrlState('uncommitted', false)
  const [realistic, setRealistic] = useUrlState('realistic', false)
  const [page, setPage] = useState(1)
  const filters: RecruitFilters = { view, position, state, stars: starFilter === 'all' ? null : Number(starFilter), q, openOnly, realistic, offset: (page - 1) * PAGE, limit: PAGE }
  const list = useRecruits(filters)
  const reset = () => setPage(1)

  return (
    <Stack gap="xs">
      {view === 'board' && (
        <Group gap="xs" wrap="wrap" align="flex-end">
          <TextInput size="xs" placeholder="Search a name" value={q} onChange={(e) => (setQ(e.currentTarget.value), reset())} w={phone ? '100%' : 180} aria-label="Search recruits" />
          <Select size="xs" placeholder="Position" clearable value={position} onChange={(v) => (setPosition(v), reset())} data={POSITIONS} w={110} aria-label="Position" />
          <Select size="xs" placeholder="Home" clearable searchable value={state} onChange={(v) => (setState(v), reset())} data={[{ value: 'INTL', label: 'Abroad' }, ...STATES]} w={110} aria-label="Home state" />
          <SegmentedControl size="xs" value={starFilter} onChange={(v) => (setStars(v), reset())} data={[{ value: 'all', label: 'All' }, { value: '5', label: '5★' }, { value: '4', label: '4★' }, { value: '3', label: '3★' }, { value: '2', label: '2★' }]} />
          <Switch size="xs" label="Uncommitted" checked={openOnly} onChange={(e) => (setOpenOnly(e.currentTarget.checked), reset())} />
          <Switch size="xs" label="Realistic for you" checked={realistic} onChange={(e) => (setRealistic(e.currentTarget.checked), reset())} title="Recruits who'd see your program's prestige as a good fit or a reach" />
        </Group>
      )}
      {list.error && <Alert color="red">{list.error.message}</Alert>}
      {list.data && list.data.total === 0 && (
        <Text c="dimmed" size="sm" py="md">
          {
            {
              board: 'No recruits match.',
              targets: 'No targets yet. Open a recruit on the Board and give him a priority: your staff spread their week over your targets.',
              offers: 'No offers out. Offer a recruit a scholarship from his card.',
              class: 'Nobody has committed yet.',
            }[view]
          }
        </Text>
      )}
      {list.data && list.data.total > 0 && (phone ? <RecruitCards recruits={list.data.recruits} onOpen={onOpen} /> : <RecruitTable recruits={list.data.recruits} onOpen={onOpen} />)}
      {list.data && list.data.total > PAGE && <Pagination size="sm" value={page} onChange={setPage} total={Math.ceil(list.data.total / PAGE)} />}
    </Stack>
  )
}

const FIT: Record<Recruit['fit'], { label: string; color: string; about: string }> = {
  good: { label: 'Good fit', color: 'teal', about: 'Your program is the size he hopes for: you can land him.' },
  reach: { label: 'Reach', color: 'yellow', about: 'He hopes for a bigger program, but the right offer and attention can win him.' },
  long_shot: { label: 'Long shot', color: 'orange', about: 'He hopes for a much bigger program: only likely if nobody bigger wants him.' },
  out_of_reach: { label: 'Out of reach', color: 'red', about: 'He expects one of the biggest programs. Your prestige grows with winning, NCAA tournament runs and titles.' },
}

/** How a recruit sees a program of your prestige. */
function Fit({ r }: { r: Recruit }) {
  if (r.status !== 'open' && !(r.status === 'committed' && r.offer_status !== 'accepted')) return null
  const f = FIT[r.fit]
  return (
    <Badge size="sm" variant="light" color={f.color} title={f.about} style={{ flexShrink: 0, overflow: 'visible' }} styles={{ label: { overflow: 'visible' } }}>
      {f.label}
    </Badge>
  )
}

function Stars({ n }: { n: number }) {
  return (
    <Text span c={n >= 5 ? 'orange' : n === 4 ? 'yellow' : 'dimmed'} size="sm" title={`${n}-star`}>
      {stars(n)}
    </Text>
  )
}

function Home({ r }: { r: Recruit }) {
  return <>{r.state ? `${r.state} #${r.state_rank}` : `${r.nation} (abroad)`}</>
}

function Where({ r }: { r: Recruit }) {
  if (r.committed_to) {
    return (
      <Text size="xs" c={r.status === 'signed' ? 'teal' : undefined}>
        {r.status === 'signed' ? 'Signed: ' : 'Committed: '}
        {r.committed_to.name}
      </Text>
    )
  }
  if (r.status === 'gone') return <Text size="xs" c="dimmed">Went elsewhere</Text>
  if (r.leader) return <Text size="xs">Leans {r.leader.name}</Text>
  return (
    <Text size="xs" c="dimmed">
      {r.offers ? `${r.offers} offer${r.offers > 1 ? 's' : ''}` : 'No offers'}
    </Text>
  )
}

function Mine({ r }: { r: Recruit }) {
  return (
    <Group gap={4} wrap="nowrap">
      {r.priority && (
        <Badge size="xs" color={PRIORITY_COLOR[r.priority]} variant="light">
          {PRIORITY_LABEL[r.priority]}
        </Badge>
      )}
      {r.offer !== null && r.offer_status !== 'pulled' && (
        <Badge size="xs" color={r.offer_status === 'accepted' ? 'teal' : r.offer_status === 'declined' ? 'red' : 'blue'} variant="outline">
          {scholarshipLabel(r.offer)}
        </Badge>
      )}
    </Group>
  )
}

function RecruitTable({ recruits, onOpen }: { recruits: Recruit[]; onOpen: (id: number) => void }) {
  return (
    <Table.ScrollContainer minWidth={900}>
      <Table highlightOnHover striped verticalSpacing={6}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th ta="right">#</Table.Th>
            <Table.Th>Recruit</Table.Th>
            <Table.Th>Pos</Table.Th>
            <Table.Th>Home</Table.Th>
            <Table.Th ta="right" title="Your staff's estimate">Ovr</Table.Th>
            <Table.Th ta="right" title="Your staff's estimate">Pot</Table.Th>
            <Table.Th title="How he sees a program of your prestige">Your chances</Table.Th>
            <Table.Th>Interest in you</Table.Th>
            <Table.Th>Where</Table.Th>
            <Table.Th>Yours</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {recruits.map((r) => (
            <Table.Tr key={r.id} style={{ cursor: 'pointer' }} onClick={() => onOpen(r.id)}>
              <Table.Td ta="right" className="fs-num">
                {r.national_rank}
              </Table.Td>
              <Table.Td>
                <Text size="sm" fw={600}>
                  {r.name}
                </Text>
                <Stars n={r.stars} />
              </Table.Td>
              <Table.Td>
                <Badge color={positionColor(r.position)} variant="light" w={44}>
                  {r.position}
                </Badge>
                <Text span size="xs" c="dimmed" ml={4}>
                  #{r.position_rank}
                </Text>
              </Table.Td>
              <Table.Td>
                <Text size="sm">
                  <Home r={r} />
                </Text>
              </Table.Td>
              <Table.Td ta="right">
                {r.overall.low}–{r.overall.high}
              </Table.Td>
              <Table.Td ta="right">
                {r.potential.low}–{r.potential.high}
              </Table.Td>
              <Table.Td miw={110} style={{ whiteSpace: 'nowrap' }}>
                <Fit r={r} />
              </Table.Td>
              <Table.Td w={130}>{r.interest !== null ? <Progress value={r.interest} size="sm" aria-label={`Interest ${Math.round(r.interest)}`} /> : <Text size="xs" c="dimmed">–</Text>}</Table.Td>
              <Table.Td>
                <Where r={r} />
              </Table.Td>
              <Table.Td>
                <Mine r={r} />
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
  )
}

function RecruitCards({ recruits, onOpen }: { recruits: Recruit[]; onOpen: (id: number) => void }) {
  return (
    <Stack gap={8}>
      {recruits.map((r) => (
        <Card key={r.id} withBorder padding="sm" className="fs-row" style={{ cursor: 'pointer' }} onClick={() => onOpen(r.id)}>
          <Group wrap="nowrap" gap="sm" align="flex-start">
            <Text className="fs-num" fz={20} w={40} ta="right" style={{ flexShrink: 0 }}>
              {r.national_rank}
            </Text>
            <div style={{ flex: 1, minWidth: 0 }}>
              <Group gap={6} wrap="nowrap">
                <Text fw={600} truncate>
                  {r.name}
                </Text>
                <Stars n={r.stars} />
                <Fit r={r} />
              </Group>
              <Text size="xs" c="dimmed" truncate>
                {r.position} #{r.position_rank} · <Home r={r} /> · ovr {r.overall.low}–{r.overall.high} · pot {r.potential.low}–{r.potential.high}
              </Text>
              <Group gap={6} mt={4} wrap="nowrap" justify="space-between">
                <Where r={r} />
                <Mine r={r} />
              </Group>
              {r.interest !== null && <Progress mt={6} value={r.interest} size={4} aria-label={`Interest ${Math.round(r.interest)}`} />}
            </div>
          </Group>
        </Card>
      ))}
    </Stack>
  )
}

function RecruitCard({ id, summary, onClose }: { id: number | null; summary: Recruiting; onClose: () => void }) {
  const { phone } = useDevice()
  const recruit = useRecruit(id)
  const r = recruit.data
  return (
    <Drawer opened={id !== null} onClose={onClose} position={phone ? 'bottom' : 'right'} size={phone ? '90%' : 'md'} title={r ? r.name : 'Recruit'}>
      {recruit.isPending && <Loader />}
      {r && <RecruitDetail key={r.id} r={r} summary={summary} />}
    </Drawer>
  )
}

function RecruitDetail({ r, summary }: { r: Recruit; summary: Recruiting }) {
  const setTarget = useSetTarget()
  const makeOffer = useMakeOffer()
  const pullOffer = usePullOffer()
  const [share, setShare] = useState<number>(Math.round(20 * (r.offer ?? r.hopes)) * 5)
  const [said, setSaid] = useState<string[]>([])
  const live = r.status === 'open' || r.status === 'committed'
  const offerOut = r.offer_status === 'open' || (r.offer_status === 'accepted' && r.status === 'committed')
  const canOffer = live && (summary.phase === 'open' || summary.phase === 'late')
  const error = setTarget.error ?? makeOffer.error ?? pullOffer.error

  return (
    <Stack gap="sm">
      <Group gap="xs">
        <Stars n={r.stars} />
        <Badge color={positionColor(r.position)} variant="light">
          {r.position}
        </Badge>
        <Text size="sm" c="dimmed">
          No. {r.national_rank} nationally · No. {r.position_rank} at {r.position} · {r.state ? `No. ${r.state_rank} in ${r.state}` : `from abroad (${r.nation})`} · age {r.age}
        </Text>
      </Group>

      <Card withBorder padding="sm">
        <Group grow>
          <div>
            <span className="fs-label">Overall when he joins</span>
            <Text className="fs-num" fz={22}>
              {r.overall.low}–{r.overall.high}
            </Text>
          </div>
          <div>
            <span className="fs-label">Potential</span>
            <Text className="fs-num" fz={22}>
              {r.potential.low}–{r.potential.high}
            </Text>
          </div>
        </Group>
        <Text size="xs" c="dimmed" mt={4}>
          Your staff’s estimate: they know him {r.knowledge >= 0.8 ? 'well' : r.knowledge >= 0.4 ? 'fairly well' : r.knowledge > 0 ? 'a little' : 'only from the rankings'}. It narrows the more they recruit him.
        </Text>
        <Progress mt={6} size={4} value={r.knowledge * 100} aria-label="How well your staff know him" />
      </Card>

      <div>
        <span className="fs-label">What he wants</span>
        <Text size="sm">{r.wants.join(' · ')}</Text>
        <Text size="sm" c="dimmed">
          Hopes for {r.hopes >= 0.95 ? 'a full scholarship' : `about a ${Math.round(r.hopes * 20) * 5}% scholarship`}
        </Text>
        <Group gap={6} mt={4} wrap="nowrap" align="flex-start">
          <Badge size="sm" variant="light" color={FIT[r.fit].color} style={{ flexShrink: 0 }}>
            {FIT[r.fit].label}
          </Badge>
          <Text size="xs" c="dimmed">
            He hopes for a program of prestige about {Math.round(r.expects)}; yours is {summary.prestige}. {FIT[r.fit].about}
          </Text>
        </Group>
      </div>

      <div>
        <span className="fs-label">Where he stands</span>
        {r.committed_to ? (
          <Text size="sm">
            {r.status === 'signed' || r.status === 'enrolled' ? 'Signed with ' : 'Committed to '}
            <ClubLink club={r.committed_to} />
          </Text>
        ) : r.status === 'gone' ? (
          <Text size="sm">Went to another level of college soccer.</Text>
        ) : r.top.length ? (
          <Stack gap={2}>
            {r.top.map((t, k) => (
              <Text size="sm" key={t.club.id}>
                {k + 1}. <ClubLink club={t.club} /> <Text span c="dimmed" size="xs">({t.share === 0 ? 'walk-on' : `${t.share}%`})</Text>
              </Text>
            ))}
          </Stack>
        ) : (
          <Text size="sm" c="dimmed">
            {r.offers ? `${r.offers} offers; your staff don't know yet where he leans.` : 'No offers yet.'}
          </Text>
        )}
        {r.interest !== null && (
          <Group gap="xs" mt={6} wrap="nowrap">
            <Text size="xs" c="dimmed" w={110}>
              Interest in you
            </Text>
            <Progress value={r.interest} style={{ flex: 1 }} aria-label={`Interest ${Math.round(r.interest)}`} />
          </Group>
        )}
      </div>

      {live && (
        <div>
          <span className="fs-label">Your priority</span>
          <SegmentedControl
            fullWidth
            value={r.priority ?? 'off'}
            disabled={setTarget.isPending}
            onChange={(v) => setTarget.mutate({ id: r.id, priority: v === 'off' ? null : (v as Priority) })}
            data={[
              { value: 'off', label: 'Off list' },
              { value: 'watch', label: 'Watch' },
              { value: 'high', label: 'High' },
              { value: 'top', label: 'Top' },
            ]}
          />
          <Text size="xs" c="dimmed" mt={4}>
            Your staff spread their week over your targets: a top target gets three times a watched one’s effort.
          </Text>
        </div>
      )}

      {canOffer && (
        <Card withBorder padding="sm">
          <span className="fs-label">{offerOut ? `Your offer: ${scholarshipLabel(r.offer ?? 0)}` : 'Scholarship offer'}</span>
          <Group align="flex-end" gap="sm" mt={4} wrap="nowrap">
            <Slider style={{ flex: 1 }} min={0} max={100} step={5} value={share} onChange={setShare} label={(v) => (v === 0 ? 'Walk-on' : `${v}%`)} aria-label="Scholarship share" />
            <NumberInput w={84} size="xs" min={0} max={100} step={5} suffix="%" value={share} onChange={(v) => setShare(Math.max(0, Math.min(100, Number(v) || 0)))} aria-label="Scholarship percent" />
          </Group>
          <Group mt="sm" gap="xs">
            <Button size="xs" loading={makeOffer.isPending} onClick={() => makeOffer.mutate({ id: r.id, share: share / 100 })}>
              {offerOut ? 'Change offer' : share === 0 ? 'Offer a walk-on place' : `Offer ${share === 100 ? 'a full scholarship' : `${share}%`}`}
            </Button>
            {offerOut && (
              <Button size="xs" variant="subtle" color="red" loading={pullOffer.isPending} onClick={() => pullOffer.mutate(r.id, { onSuccess: (news) => setSaid(news) })}>
                {r.status === 'committed' ? 'Pull his scholarship' : 'Pull offer'}
              </Button>
            )}
          </Group>
          <Text size="xs" c="dimmed" mt={6}>
            Offers out and your class together may be worth up to {summary.offer_limit.toFixed(2)} scholarships. A recruit can only commit while you have the money and a place for him.
          </Text>
        </Card>
      )}
      {!canOffer && live && summary.phase === 'before' && (
        <Text size="sm" c="dimmed">
          Offers open {longDate(summary.start)}. Put him on your list now and your staff start getting to know him.
        </Text>
      )}
      {error && <Alert color="red">{error.message}</Alert>}
      {said.map((m) => (
        <Alert key={m} color="yellow">
          {m}
        </Alert>
      ))}
    </Stack>
  )
}

function ClassRankings() {
  const ranks = useClassRankings()
  if (ranks.isPending) return <Loader />
  if (ranks.error) return <Alert color="red">{ranks.error.message}</Alert>
  if (!ranks.data.length) return <Text c="dimmed">No commitments yet: the class rankings start with the first.</Text>
  return (
    <Table striped verticalSpacing={6}>
      <Table.Thead>
        <Table.Tr>
          <Table.Th ta="right">#</Table.Th>
          <Table.Th>Program</Table.Th>
          <Table.Th ta="right">Recruits</Table.Th>
          <Table.Th visibleFrom="sm">Stars</Table.Th>
          <Table.Th ta="right">Points</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {ranks.data.map((c) => (
          <Table.Tr key={c.club.id} bg={c.mine ? 'var(--fs-surface-2)' : undefined} fw={c.mine ? 700 : undefined}>
            <Table.Td ta="right" className="fs-num">
              {c.rank}
            </Table.Td>
            <Table.Td>
              <UnstyledButton>
                <ClubLink club={c.club} />
              </UnstyledButton>
            </Table.Td>
            <Table.Td ta="right">{c.recruits}</Table.Td>
            <Table.Td visibleFrom="sm">
              <Text size="xs" c="dimmed">
                {[5, 4, 3, 2]
                  .filter((n) => c.stars[n])
                  .map((n) => `${c.stars[n]}×${n}★`)
                  .join('  ')}
              </Text>
            </Table.Td>
            <Table.Td ta="right" className="fs-num">
              {c.points}
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  )
}
