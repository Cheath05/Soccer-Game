import { Badge, Button, Card, Grid, Group, Loader, Modal, Progress, SegmentedControl, Select, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core'
import { useNavigate, useParams } from '@tanstack/react-router'
import { useEffect, useState } from 'react'

import { useClubPlayers, usePlayer, usePlayerSeasons, useReleasePlayer } from '../api/hooks'
import { type Training, useSetTraining, useTraining } from '../api/training'
import { type AvailabilityStatus, useAvailability, useSetAvailability } from '../api/transfers'
import BackButton from '../components/BackButton'
import type { FamiliarityBand, PlayerSeasonLine, PositionRating } from '../api/types'
import ClubLink from '../components/ClubLink'
import { SeasonChange } from '../components/SeasonChange'
import { recallPlayerList } from '../lib/playerList'
import { attributeLabel, matchRatingColor, money, positionColor, ratingColor, wage } from '../lib/format'

const GROUP_TITLES: Record<string, string> = {
  technical: 'Technical',
  mental: 'Mental',
  physical: 'Physical',
  defensive: 'Defending',
  goalkeeping: 'Goalkeeping',
}

export default function PlayerPage() {
  const { playerId } = useParams({ from: '/players/$playerId' })
  const player = usePlayer(Number(playerId))
  const navigate = useNavigate()
  const clubPlayers = useClubPlayers(player.data?.club?.id ?? 0)
  // The list he was opened from (the squad as sorted and filtered), else his club's squad.
  const remembered = recallPlayerList()
  const order = remembered.includes(Number(playerId)) ? remembered : (clubPlayers.data ?? []).map((c) => c.id)
  const at = order.indexOf(Number(playerId))
  const previous = at > 0 ? order[at - 1] : undefined
  const next = at >= 0 && at < order.length - 1 ? order[at + 1] : undefined
  const names = new Map((clubPlayers.data ?? []).map((c) => [c.id, c.name]))
  const go = (id: number | undefined) => {
    if (id !== undefined) void navigate({ to: '/players/$playerId', params: { playerId: String(id) }, replace: true })
  }

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return
      if (target && (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable)) return
      if (document.querySelector('[role="dialog"]')) return
      if (event.key === 'ArrowLeft' && previous !== undefined) go(previous)
      else if (event.key === 'ArrowRight' && next !== undefined) go(next)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previous, next])

  if (player.isPending) return <Loader />
  if (!player.data) return <Text c="red">{player.error?.message}</Text>
  const p = player.data
  const keeper = p.position === 'GK'
  const groups = keeper
    ? ['goalkeeping', 'physical', 'mental', 'technical']
    : ['technical', 'mental', 'physical', 'defensive']

  return (
    <Stack>
      <Group justify="space-between">
        <BackButton fallback="/squad" />
        {order.length > 1 && (
          <Group gap="xs">
            <Button variant="default" size="compact-sm" disabled={previous === undefined} onClick={() => go(previous)} title={previous !== undefined ? names.get(previous) : undefined}>
              ‹ Previous
            </Button>
            <Text size="xs" c="dimmed">
              {at >= 0 ? `${at + 1} of ${order.length}` : ''}
            </Text>
            <Button variant="default" size="compact-sm" disabled={next === undefined} onClick={() => go(next)} title={next !== undefined ? names.get(next) : undefined}>
              Next ›
            </Button>
          </Group>
        )}
      </Group>
      <Group justify="space-between" align="start">
        <div>
          <Title order={2}>{p.name}</Title>
          <Text c="dimmed">
            {p.age} years · {p.nationality ?? 'Unknown'} · {p.club ? <ClubLink club={p.club} /> : p.retired ? 'Retired' : 'Free agent'}
          </Text>
          <Group gap={6} mt={6}>
            {Object.entries(p.familiarity)
              .filter(([, f]) => f >= 15)
              .sort((a, b) => b[1] - a[1])
              .map(([pos]) => (
                <Badge key={pos} color={positionColor(pos)} variant={pos === p.position ? 'filled' : 'light'}>
                  {pos}
                </Badge>
              ))}
          </Group>
        </div>
        <Group>
          {p.own_player && <ReleaseButton playerId={p.id} name={p.name} />}
          <Card withBorder padding="sm" ta="center" miw={90}>
            <Text size="xs" c="dimmed">
              Overall
            </Text>
            <Text fz={32} fw={800} c={ratingColor(p.overall)}>
              {p.overall}
            </Text>
            {!!p.trend && (
              <Text size="xs" fw={600} c={p.trend > 0 ? 'green.7' : 'red.7'}>
                {p.trend > 0 ? '▲ Rising lately' : '▼ Falling lately'}
              </Text>
            )}
            {p.season_start_overall != null && (
              <Text size="xs" c="dimmed">
                Start of season {p.season_start_overall}
                {p.overall !== p.season_start_overall && (
                  <>
                    {' · '}
                    <SeasonChange start={p.season_start_overall} now={p.overall} />
                  </>
                )}
              </Text>
            )}
          </Card>
          <Card withBorder padding="sm" ta="center" miw={150}>
            <Text size="xs" c="dimmed">
              Potential (scouted)
            </Text>
            <Text fz={22} fw={700}>
              {p.potential.low === p.potential.high ? p.potential.low : `${p.potential.low}–${p.potential.high}`}
            </Text>
            <Text size="xs">{p.potential.label}</Text>
          </Card>
        </Group>
      </Group>

      <Stack gap={4}>
        <SimpleGrid cols={{ base: 3, sm: 6 }}>
          {Object.entries(p.face).map(([k, v]) => {
            const key = (p.face_key ?? []).includes(k)
            return (
              <Card
                key={k}
                withBorder
                padding="xs"
                ta="center"
                style={key ? { borderColor: 'var(--mantine-primary-color-filled)' } : undefined}
              >
                <Text size="xs" c={key ? undefined : 'dimmed'} fw={key ? 700 : undefined}>
                  {k}
                </Text>
                <Text fw={700} fz="xl" c={ratingColor(v)}>
                  {v}
                </Text>
              </Card>
            )
          })}
        </SimpleGrid>
        <Text size="xs" c="dimmed">
          Outlined: the ratings that count most towards a {p.position}&apos;s overall. Every one of them counts
          for something.
        </Text>
      </Stack>

      <Grid>
        <Grid.Col span={{ base: 12, md: 8 }}>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            {groups.map((g) => (
              <Card key={g} withBorder padding="sm">
                <Text fw={600} mb={4}>
                  {GROUP_TITLES[g]}
                </Text>
                {(p.attributes[g] ?? []).map((a) => (
                  <Group key={a.key} justify="space-between" gap={4}>
                    <Text size="sm">{attributeLabel(a.key)}</Text>
                    <Text size="sm" fw={700} c={ratingColor(a.value)}>
                      {a.value}
                    </Text>
                  </Group>
                ))}
              </Card>
            ))}
          </SimpleGrid>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Stack>
            <Card withBorder padding="sm">
              <Text fw={600} mb={4}>
                Best roles
              </Text>
              {p.roles.map((r) => (
                <Group key={r.key} justify="space-between">
                  <Text size="sm">{r.name}</Text>
                  <Text size="sm" fw={700} c={ratingColor(r.rating)}>
                    {r.rating}
                  </Text>
                </Group>
              ))}
            </Card>
            <Card withBorder padding="sm">
              <Text fw={600} mb={4}>
                Details
              </Text>
              <Table verticalSpacing={2}>
                <Table.Tbody>
                  <Row label="Height" value={p.height_cm ? `${p.height_cm} cm` : '–'} />
                  <Row label="Weight" value={p.weight_kg ? `${p.weight_kg} kg` : '–'} />
                  <Row label="Foot" value={`${p.preferred_foot} (weak foot ${p.weak_foot}★)`} />
                  <Row label="Skill moves" value={`${p.skill_moves}★`} />
                  <Row label="Value" value={money(p.value_eur)} />
                  {p.wage_weekly_eur !== null && <Row label="Wage" value={wage(p.wage_weekly_eur)} />}
                  <Row label="Contract" value={`until ${p.contract_end}`} />
                  {p.condition !== null && <Row label="Condition" value={`${p.condition}%`} />}
                  <Row label="Season" value={`${p.appearances} apps · ${p.goals} goals · ${p.assists} assists`} />
                  {p.average_rating !== null && <Row label="Avg rating" value={p.average_rating.toFixed(2)} />}
                </Table.Tbody>
              </Table>
            </Card>
            {p.traits.length > 0 && (
              <Card withBorder padding="sm">
                <Text fw={600} mb={4}>
                  Traits
                </Text>
                <Group gap={6}>
                  {p.traits.map((t) => (
                    <Badge key={t} variant="outline">
                      {t.replaceAll('_', ' ')}
                    </Badge>
                  ))}
                </Group>
              </Card>
            )}
          </Stack>
        </Grid.Col>
      </Grid>

      <PositionsCard playerId={p.id} ratings={p.position_ratings ?? []} own={p.own_player} />

      {p.own_player && <TrainingCard playerId={p.id} familiarity={p.familiarity} ratings={p.position_ratings ?? []} />}
      {p.own_player && <AvailabilityCard playerId={p.id} />}

      <SeasonRecord playerId={p.id} />
    </Stack>
  )
}

/** The player's record season by season, the current one first: a line for each competition
 * and a total. A retired player keeps his. */
function SeasonRecord({ playerId }: { playerId: number }) {
  const seasons = usePlayerSeasons(playerId).data
  if (!seasons) return null
  const cells = (line: PlayerSeasonLine) => (
    <>
      <Table.Td ta="right">{line.appearances}</Table.Td>
      <Table.Td ta="right">{line.starts}</Table.Td>
      <Table.Td ta="right">{line.minutes}</Table.Td>
      <Table.Td ta="right">{line.goals}</Table.Td>
      <Table.Td ta="right">{line.assists}</Table.Td>
      <Table.Td ta="right">
        {line.average_rating !== null && (
          <Text size="sm" fw={600} c={matchRatingColor(line.average_rating)} span>
            {line.average_rating.toFixed(2)}
          </Text>
        )}
      </Table.Td>
      <Table.Td ta="right">{line.yellow}</Table.Td>
      <Table.Td ta="right">{line.red}</Table.Td>
    </>
  )
  return (
    <Card withBorder padding="sm" aria-label="Seasons">
      <Title order={4} mb={4}>
        Seasons
      </Title>
      {seasons.length === 0 ? (
        <Text size="sm" c="dimmed">
          No matches played yet.
        </Text>
      ) : (
        <Table.ScrollContainer minWidth={760}>
          <Table verticalSpacing={4}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Season</Table.Th>
                <Table.Th>Club</Table.Th>
                <Table.Th>Competition</Table.Th>
                <Table.Th ta="right">Apps</Table.Th>
                <Table.Th ta="right">Starts</Table.Th>
                <Table.Th ta="right">Mins</Table.Th>
                <Table.Th ta="right">Goals</Table.Th>
                <Table.Th ta="right">Assists</Table.Th>
                <Table.Th ta="right">Rating</Table.Th>
                <Table.Th ta="right">YC</Table.Th>
                <Table.Th ta="right">RC</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {seasons.flatMap((s) => [
                ...s.lines.map((line, i) => (
                  <Table.Tr key={`${s.season_id}-${line.competition_key}-${line.club?.id}`}>
                    <Table.Td fw={600}>{i === 0 ? s.season : ''}</Table.Td>
                    <Table.Td>{line.club ? <ClubLink club={line.club} /> : '–'}</Table.Td>
                    <Table.Td>{line.competition}</Table.Td>
                    {cells(line)}
                  </Table.Tr>
                )),
                <Table.Tr key={`${s.season_id}-total`} fw={700} bg="var(--mantine-color-default-hover)">
                  <Table.Td />
                  <Table.Td />
                  <Table.Td>Total {s.season}</Table.Td>
                  {cells(s.total)}
                </Table.Tr>,
              ])}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </Card>
  )
}

const TRAIN_POSITIONS = ['GK', 'CB', 'LB', 'RB', 'LWB', 'RWB', 'DM', 'CM', 'AM', 'LM', 'RM', 'LW', 'RW', 'ST']

const BAND_COLOR: Record<FamiliarityBand, string> = {
  natural: 'green',
  accomplished: 'teal',
  competent: 'yellow',
  awkward: 'orange',
  unconvincing: 'red',
}
const BAND_HINT: Record<FamiliarityBand, string> = {
  natural: 'natural',
  accomplished: 'accomplished, not yet natural',
  competent: 'competent, not yet natural',
  awkward: 'awkward, not yet natural',
  unconvincing: 'unconvincing, not yet natural',
}

/** Months until the position being trained is natural, from the training rate (at least 1). */
function monthsLeft(t: Training, familiarity: number): number | null {
  if (!t.position || t.rate_per_month <= 0) return null
  return Math.max(1, Math.ceil((t.natural - familiarity - t.progress) / t.rate_per_month))
}

const monthsText = (m: number) => `about ${m} ${m === 1 ? 'month' : 'months'} left`

/** His rating at every position, with the cost of not being natural there; on the user's own
 * players, a Train action on each position he isn't natural in. */
function PositionsCard({ playerId, ratings, own }: { playerId: number; ratings: PositionRating[]; own: boolean }) {
  const training = useTraining(playerId, own)
  const set = useSetTraining(playerId)
  const t = training.data
  return (
    <Card withBorder padding="sm" aria-label="Positions">
      <Title order={4} mb={4}>
        Positions
      </Title>
      <Text size="xs" c="dimmed" mb="xs">
        A player rates his full ability only in positions he&apos;s natural in (18+ familiarity). Elsewhere a familiarity penalty applies: accomplished −3%, competent −7%, awkward −15%.
      </Text>
      <Stack gap={6}>
        {ratings.map((r) => {
          const loss = r.full_rating - r.rating
          const trained = t?.position === r.position
          const have = t?.positions.find((x) => x.position === r.position)?.familiarity ?? r.familiarity
          const months = trained && t ? monthsLeft(t, have) : null
          return (
            <Group key={r.position} gap="xs" wrap="nowrap" align="center">
              <Badge color={positionColor(r.position)} variant={r.primary ? 'filled' : 'light'} w={52} title={r.name}>
                {r.position}
              </Badge>
              <Text size="xs" c="dimmed" w={40}>
                {r.primary ? 'Main' : ''}
              </Text>
              <Badge color={BAND_COLOR[r.band]} variant="light" w={110}>
                {r.band}
              </Badge>
              <Text size="sm" style={{ flex: 1 }}>
                <Text span fw={700} c={ratingColor(r.rating)}>
                  {r.rating}
                </Text>
                {loss > 0 && (
                  <Text span c="dimmed">
                    {' '}
                    (−{loss}: {BAND_HINT[r.band]})
                  </Text>
                )}
                {trained && (
                  <Text span size="xs" c="blue.7" fw={600}>
                    {' '}
                    · training{months !== null ? `, ${monthsText(months)}` : ''}
                  </Text>
                )}
              </Text>
              <Progress value={Math.min(100, (r.familiarity / 18) * 100)} w={70} title={`Familiarity ${r.familiarity} of 18`} />
              <Text size="xs" c="dimmed" w={34} ta="right">
                {r.familiarity}/18
              </Text>
              {own && (
                <div style={{ width: 64 }}>
                  {r.band !== 'natural' &&
                    (trained ? (
                      <Button size="compact-xs" variant="default" loading={set.isPending} onClick={() => set.mutate(null)}>
                        Stop
                      </Button>
                    ) : (
                      <Button size="compact-xs" loading={set.isPending} onClick={() => set.mutate(r.position)}>
                        Train
                      </Button>
                    ))}
                </div>
              )}
            </Group>
          )
        })}
      </Stack>
      {set.error && (
        <Text c="red" size="sm" mt="xs">
          {set.error.message}
        </Text>
      )}
    </Card>
  )
}

/** Teach one of the user's players a new position, one at a time. */
function TrainingCard({ playerId, familiarity, ratings }: { playerId: number; familiarity: Record<string, number>; ratings: PositionRating[] }) {
  const training = useTraining(playerId, true)
  const set = useSetTraining(playerId)
  const [choice, setChoice] = useState<string | null>(null)
  const t = training.data
  if (!t) return null
  const fam = new Map<string, number>(Object.entries(familiarity))
  for (const row of t.positions) fam.set(row.position, row.familiarity)
  const options = TRAIN_POSITIONS.filter((pos) => (fam.get(pos) ?? 0) < t.natural)
  const current = t.position
  const have = current ? (fam.get(current) ?? 0) : 0
  const months = monthsLeft(t, have)
  const rating = (pos: string | null) => ratings.find((r) => r.position === pos)
  const now = rating(current)
  const picked = rating(choice)
  return (
    <Card withBorder padding="sm" aria-label="Position training">
      <Title order={4} mb={4}>
        Position training
      </Title>
      <Text size="xs" c="dimmed" mb="xs">
        Training works on one position at a time. When it finishes he is natural there, so he plays it at his full rating with no penalty, and you can then train another. It doesn&apos;t change his attributes.
      </Text>
      <Stack gap="xs">
        {current ? (
          <>
            <Group justify="space-between">
              <Text size="sm" fw={600}>
                Training {current}
              </Text>
              <Button size="compact-xs" variant="default" color="red" loading={set.isPending} onClick={() => set.mutate(null)}>
                Stop
              </Button>
            </Group>
            <Progress value={Math.round(t.progress * 100)} />
            <Text size="xs" c="dimmed">
              Familiarity {have} of {t.natural}
              {months !== null ? ` · ${monthsText(months)} until natural` : ''}
              {now ? ` · rates ${now.rating} there now, ${now.full_rating} when natural` : ''}
            </Text>
          </>
        ) : (
          <Text size="sm" c="dimmed">
            Not training a new position.
          </Text>
        )}
        <Group align="flex-end" gap="xs">
          <Select label={current ? 'Switch to' : 'Learn'} placeholder="Position" data={options} value={choice} onChange={setChoice} w={140} />
          <Button disabled={!choice} loading={set.isPending} onClick={() => choice && set.mutate(choice, { onSuccess: () => setChoice(null) })}>
            Train
          </Button>
          {picked && (
            <Text size="sm" c="dimmed">
              Rates {picked.rating} there now, {picked.full_rating} when natural
            </Text>
          )}
        </Group>
        {set.error && (
          <Text c="red" size="sm">
            {set.error.message}
          </Text>
        )}
      </Stack>
    </Card>
  )
}

/** Not for sale, on the transfer list (clubs bid to buy him) or on the loan list (clubs ask to borrow him). */
function AvailabilityCard({ playerId }: { playerId: number }) {
  const availability = useAvailability().data
  const set = useSetAvailability()
  const status: AvailabilityStatus = availability?.transfer.includes(playerId) ? 'transfer' : availability?.loan.includes(playerId) ? 'loan' : 'none'
  const hint: Record<AvailabilityStatus, string> = {
    none: 'He stays with you. Clubs may still make an offer, which you can turn down.',
    transfer: 'Clubs bid to buy him. Offers arrive under Transfers, in Offers for your players, over the following days while the window is open.',
    loan: 'Clubs that need cover ask to borrow him for the season, at any age. Offers arrive under Transfers, in Offers for your players, while the window is open.',
  }
  return (
    <Card withBorder padding="sm" aria-label="Availability">
      <Title order={4} mb={4}>
        Up for sale, or up for loan
      </Title>
      <SegmentedControl
        value={status}
        disabled={!availability || set.isPending}
        onChange={(v) => set.mutate({ playerId, status: v as AvailabilityStatus })}
        data={[
          { value: 'none', label: 'Not for sale' },
          { value: 'transfer', label: 'Transfer list' },
          { value: 'loan', label: 'Loan list' },
        ]}
      />
      <Text size="xs" c="dimmed" mt={6}>
        {hint[status]}
      </Text>
      {set.error && (
        <Text c="red" size="sm">
          {set.error.message}
        </Text>
      )}
    </Card>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <Table.Tr>
      <Table.Td c="dimmed">{label}</Table.Td>
      <Table.Td>{value}</Table.Td>
    </Table.Tr>
  )
}

function ReleaseButton({ playerId, name }: { playerId: number; name: string }) {
  const [opened, setOpened] = useState(false)
  const release = useReleasePlayer()
  return (
    <>
      <Button variant="subtle" color="red" size="xs" onClick={() => setOpened(true)}>
        Release
      </Button>
      <Modal opened={opened} onClose={() => setOpened(false)} title={`Release ${name}?`} centered>
        <Stack>
          <Text size="sm">His contract ends today and he leaves as a free agent. Until transfers are in the game, a released player isn&apos;t signed by anyone, and most leave the professional game at the end of the season.</Text>
          {release.error && (
            <Text c="red" size="sm">
              {release.error.message}
            </Text>
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setOpened(false)}>
              Keep him
            </Button>
            <Button color="red" loading={release.isPending} onClick={() => release.mutate(playerId, { onSuccess: () => setOpened(false) })}>
              Release
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  )
}
