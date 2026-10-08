import { Badge, Button, Card, Grid, Group, Loader, Modal, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core'
import { useNavigate, useParams, useRouter } from '@tanstack/react-router'
import { useEffect, useState } from 'react'

import { useClubPlayers, usePlayer, usePlayerSeasons, useReleasePlayer } from '../api/hooks'
import type { PlayerSeasonLine } from '../api/types'
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
  const router = useRouter()
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
  const back = () => (window.history.length > 1 ? router.history.back() : void navigate({ to: '/squad' }))

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
        <Button variant="subtle" size="compact-sm" onClick={back}>
          ← Back
        </Button>
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
