import { Badge, Button, Card, Group, Loader, SegmentedControl, Select, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core'
import { Link } from '@tanstack/react-router'

import { type Conference, useBracket, useConferences, useDraftPool, useRankings } from '../api/americas'
import { ApiError } from '../api/client'
import { useCareer } from '../api/hooks'
import CollegeBracket from '../components/CollegeBracket'
import ClubLink from '../components/ClubLink'
import PlayerLink from '../components/PlayerLink'
import { positionColor, ratingColor } from '../lib/format'
import { useDevice } from '../lib/device'
import { useUrlState } from '../lib/urlState'

// US college soccer (W9a; api/college.py, docs/plans/w9a-ncaa-notes.md): NCAA Division I's
// conference tables and tournaments, the RPI, the NCAA tournament and the draft pool that feeds
// MLS's SuperDraft.

const TABS = [
  { value: 'tables', label: 'Conferences' },
  { value: 'rpi', label: 'RPI' },
  { value: 'ncaa', label: 'NCAA' },
  { value: 'draft', label: 'Draft pool' },
]

const GROUPS: Record<string, string[]> = {
  All: [],
  GK: ['GK'],
  DEF: ['CB', 'LB', 'RB', 'LWB', 'RWB'],
  MID: ['DM', 'CM', 'AM', 'LM', 'RM'],
  ATT: ['LW', 'RW', 'ST'],
}

export default function CollegePage() {
  const conferences = useConferences()
  const [tab, setTab] = useUrlState('tab', 'tables')
  const missing = conferences.error instanceof ApiError && conferences.error.status === 404

  return (
    <Stack gap="sm">
      <div>
        <Title order={2}>College soccer</Title>
        <Text size="sm" c="dimmed">
          NCAA Division I men’s soccer: where MLS’s SuperDraft finds its players
        </Text>
      </div>
      {conferences.isPending ? (
        <Loader />
      ) : missing ? (
        <Card className="fs-hero" padding="lg">
          <span className="fs-label">Starts next season</span>
          <Text mt={6}>College soccer joined the game after this career began. Its 213 programs start playing next season: the conference tables, the NCAA tournament and the draft pool will be here then.</Text>
        </Card>
      ) : !conferences.data ? (
        <Text c="red">{conferences.error?.message}</Text>
      ) : (
        <>
          <SegmentedControl fullWidth value={tab} onChange={setTab} data={TABS} aria-label="College view" />
          {tab === 'tables' && <Conferences list={conferences.data} />}
          {tab === 'rpi' && <Rankings />}
          {tab === 'ncaa' && <NcaaBracket />}
          {tab === 'draft' && <DraftPool />}
        </>
      )}
    </Stack>
  )
}

function Conferences({ list }: { list: Conference[] }) {
  const { phone } = useDevice()
  const [key, setKey] = useUrlState<string | null>('conf', null)
  const [view, setView] = useUrlState('view', 'table')
  // A college coach (W9c) opens on their own conference.
  const own = useCareer().data?.college?.conference
  const conf = list.find((c) => c.key === key) ?? list.find((c) => c.key === own) ?? list[0]
  const hasTournament = (conf?.tournament ?? 0) >= 2
  const showBracket = view === 'tournament' && hasTournament
  const bracket = useBracket(`CT:${conf?.key}`, !!conf && showBracket)
  if (!conf) return null
  const data = [...list].sort((a, b) => a.short_name.localeCompare(b.short_name)).map((c) => ({ value: c.key, label: c.short_name }))

  return (
    <Stack gap="sm">
      <Group gap="xs" wrap={phone ? 'wrap' : 'nowrap'}>
        <Select
          aria-label="Conference"
          searchable
          w={phone ? '100%' : 260}
          value={conf.key}
          onChange={(v) => v && setKey(v)}
          allowDeselect={false}
          data={data}
        />
        {hasTournament && (
          <SegmentedControl
            aria-label="Table or tournament"
            value={showBracket ? 'tournament' : 'table'}
            onChange={setView}
            data={[
              { value: 'table', label: 'Table' },
              { value: 'tournament', label: 'Tournament' },
            ]}
          />
        )}
      </Group>
      <SimpleGrid cols={{ base: 2, sm: 3 }} spacing="sm">
        <Fact label="Regular season" value={conf.regular_season_champion} />
        {hasTournament && <Fact label="Tournament" value={conf.tournament_champion} />}
        <Card withBorder padding="sm" visibleFrom="sm">
          <span className="fs-label">Format</span>
          <Text fw={600}>{conf.rows.length} teams</Text>
          <Text size="xs" c="dimmed">
            {hasTournament ? `Top ${conf.tournament} go to the ${conf.short_name} Tournament` : 'The table’s winner takes the automatic bid'}
          </Text>
        </Card>
      </SimpleGrid>
      {showBracket ? (
        bracket.data ? (
          <CollegeBracket bracket={bracket.data} empty={`The ${conf.short_name} Tournament starts in November, with the table’s top ${conf.tournament}.`} />
        ) : bracket.isPending ? (
          <Loader />
        ) : (
          <Text c="red">{bracket.error?.message}</Text>
        )
      ) : (
        <Card withBorder padding={phone ? 'xs' : 'sm'}>
          <Text fw={600} mb={4} px={4}>
            {conf.name}
          </Text>
          <Table highlightOnHover verticalSpacing={5}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={34}>#</Table.Th>
                <Table.Th>Club</Table.Th>
                <Table.Th ta="right">P</Table.Th>
                <Table.Th ta="right" visibleFrom="sm">W</Table.Th>
                <Table.Th ta="right" visibleFrom="sm">D</Table.Th>
                <Table.Th ta="right" visibleFrom="sm">L</Table.Th>
                <Table.Th ta="right" visibleFrom="sm">GF</Table.Th>
                <Table.Th ta="right" visibleFrom="sm">GA</Table.Th>
                <Table.Th ta="right">GD</Table.Th>
                <Table.Th ta="right">Pts</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {conf.rows.map((r) => {
                const gd = r.goals_for - r.goals_against
                return (
                  <Table.Tr key={r.club.id} className={r.in_tournament ? 'fs-qualify' : undefined}>
                    <Table.Td c="dimmed" className="fs-num">
                      {r.position}
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm" component="span" fw={500}>
                        <ClubLink club={r.club} />
                      </Text>
                    </Table.Td>
                    <Table.Td ta="right" c="dimmed">{r.played}</Table.Td>
                    <Table.Td ta="right" visibleFrom="sm">{r.won}</Table.Td>
                    <Table.Td ta="right" visibleFrom="sm">{r.drawn}</Table.Td>
                    <Table.Td ta="right" visibleFrom="sm">{r.lost}</Table.Td>
                    <Table.Td ta="right" visibleFrom="sm">{r.goals_for}</Table.Td>
                    <Table.Td ta="right" visibleFrom="sm">{r.goals_against}</Table.Td>
                    <Table.Td ta="right" c="dimmed">{gd > 0 ? `+${gd}` : gd}</Table.Td>
                    <Table.Td ta="right" className="fs-num" fz={16}>
                      {r.points}
                    </Table.Td>
                  </Table.Tr>
                )
              })}
            </Table.Tbody>
          </Table>
          <Text size="xs" c="dimmed" mt={6} px={4}>
            Conference games only. {hasTournament ? `The marked places go to the ${conf.short_name} Tournament; its winner gets the NCAA’s automatic bid.` : 'The top place takes the NCAA’s automatic bid.'}
          </Text>
        </Card>
      )}
    </Stack>
  )
}

function Rankings() {
  const rankings = useRankings(true)
  if (rankings.isPending) return <Loader />
  if (!rankings.data) return <Text c="red">{rankings.error?.message}</Text>
  if (rankings.data.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        The RPI starts once the college season has games to rate (from late August).
      </Text>
    )
  }
  return (
    <Card withBorder padding="sm">
      <Text size="xs" c="dimmed" mb={4}>
        The Rating Percentage Index: a quarter a team’s own winning share, half its opponents’, a quarter their opponents’. The NCAA’s 25 at-large bids and its seeds follow it.
      </Text>
      <Table highlightOnHover verticalSpacing={5}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th w={40}>#</Table.Th>
            <Table.Th>Club</Table.Th>
            <Table.Th>Conference</Table.Th>
            <Table.Th ta="right">RPI</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rankings.data.map((r) => (
            <Table.Tr key={r.club.id}>
              <Table.Td className="fs-num" c={r.rank <= 16 ? 'teal' : 'dimmed'}>
                {r.rank}
              </Table.Td>
              <Table.Td>
                <Text size="sm" component="span" fw={500}>
                  <ClubLink club={r.club} />
                </Text>
              </Table.Td>
              <Table.Td>
                <Text size="sm" c="dimmed" component="span">
                  {r.conference}
                </Text>
              </Table.Td>
              <Table.Td ta="right" className="fs-num">
                {r.rpi.toFixed(4)}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Card>
  )
}

function NcaaBracket() {
  const bracket = useBracket('NCAA', true)
  if (bracket.isPending) return <Loader />
  if (!bracket.data) return <Text c="red">{bracket.error?.message}</Text>
  const b = bracket.data
  const auto = b.entrants.filter((e) => e.bid === 'auto').length
  const atLarge = b.entrants.filter((e) => e.bid === 'at_large').length
  return (
    <Stack gap="sm">
      <Group justify="space-between" align="baseline">
        <Title order={3}>
          {b.name}{' '}
          <Text span c="dimmed" fz="md">
            {b.season}
          </Text>
        </Title>
        {b.entrants.length > 0 && (
          <Text size="xs" c="dimmed">
            {b.entrants.length} teams: {auto} automatic bids, {atLarge} at-large · seeds 1–{b.seeded} start in the second round
          </Text>
        )}
      </Group>
      <CollegeBracket bracket={b} empty="The 48-team field is picked on 16 November, after the conference tournaments: the 23 conference champions and the best 25 of the rest by the RPI. The College Cup, the semifinals and the final, is in mid-December." />
    </Stack>
  )
}

function DraftPool() {
  const { phone } = useDevice()
  const pool = useDraftPool(true)
  const [group, setGroup] = useUrlState('group', 'All')
  if (pool.isPending) return <Loader />
  if (!pool.data) return <Text c="red">{pool.error?.message}</Text>
  // The server's order counts the hidden potential: by overall instead, so the list doesn't give it away.
  const rows = pool.data
    .filter((p) => group === 'All' || GROUPS[group].includes(p.position))
    .sort((a, b) => b.overall - a.overall || a.age - b.age || a.name.localeCompare(b.name))

  return (
    <Stack gap="sm">
      <Group>
        <Button component={Link} to="/draft" size="compact-sm" variant="light">
          The SuperDraft: rank your picks
        </Button>
      </Group>
      <Text size="sm" c="dimmed">
        After the College Cup final every senior declares for MLS’s SuperDraft in January, with a few underclassmen signed by Generation adidas (GA). Those not drafted become free agents in February.
      </Text>
      {pool.data.length === 0 ? (
        <Text size="sm" c="dimmed">
          No prospects yet: they declare once the College Cup final is played in December.
        </Text>
      ) : (
        <>
          <Group justify="space-between">
            <Text size="sm" fw={600}>
              {rows.length} prospects
            </Text>
            <SegmentedControl size="xs" value={group} onChange={setGroup} data={Object.keys(GROUPS)} />
          </Group>
          {phone ? (
            <Stack gap={8}>
              {rows.slice(0, 200).map((p) => (
                <Card key={p.player_id} withBorder padding="sm" className="fs-row">
                  <Group wrap="nowrap" gap="sm">
                    <Badge color={positionColor(p.position)} variant="light" w={46} style={{ flexShrink: 0 }}>
                      {p.position}
                    </Badge>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <Group gap={6} wrap="nowrap">
                        <Text fw={600} truncate>
                          <PlayerLink player={{ id: p.player_id, name: p.name }} />
                        </Text>
                        {p.ga && <Badge size="xs" color="cyan" style={{ flexShrink: 0 }}>GA</Badge>}
                      </Group>
                      <Text size="xs" c="dimmed" truncate>
                        {p.college.name} · {p.class_year} · {p.age}y
                      </Text>
                    </div>
                    <Text className="fs-num" fz={26} lh={1} c={ratingColor(p.overall)} style={{ flexShrink: 0 }}>
                      {p.overall}
                    </Text>
                  </Group>
                </Card>
              ))}
            </Stack>
          ) : (
            <Table.ScrollContainer minWidth={640}>
              <Table highlightOnHover striped verticalSpacing={5}>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th w={60}>Pos</Table.Th>
                    <Table.Th>Name</Table.Th>
                    <Table.Th>College</Table.Th>
                    <Table.Th>Class</Table.Th>
                    <Table.Th ta="right">Age</Table.Th>
                    <Table.Th ta="right">Ovr</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {rows.slice(0, 300).map((p) => (
                    <Table.Tr key={p.player_id}>
                      <Table.Td>
                        <Badge color={positionColor(p.position)} variant="light" w={44}>
                          {p.position}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Group gap={6} wrap="nowrap">
                          <Text size="sm" fw={500} component="span">
                            <PlayerLink player={{ id: p.player_id, name: p.name }} />
                          </Text>
                          {p.ga && <Badge size="xs" color="cyan">GA</Badge>}
                        </Group>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm" component="span">
                          <ClubLink club={p.college} />
                        </Text>
                      </Table.Td>
                      <Table.Td>{p.class_year}</Table.Td>
                      <Table.Td ta="right">{p.age}</Table.Td>
                      <Table.Td ta="right">
                        <Text fw={700} size="sm" c={ratingColor(p.overall)} span>
                          {p.overall}
                        </Text>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
          {rows.length > (phone ? 200 : 300) && (
            <Text size="xs" c="dimmed">
              The best {phone ? 200 : 300} shown.
            </Text>
          )}
        </>
      )}
    </Stack>
  )
}

function Fact({ label, value }: { label: string; value: { id: number; name: string } | null }) {
  return (
    <Card withBorder padding="sm">
      <span className="fs-label">{label} champions</span>
      <Text fw={600} truncate>
        {value ? <ClubLink club={value} /> : '–'}
      </Text>
    </Card>
  )
}
