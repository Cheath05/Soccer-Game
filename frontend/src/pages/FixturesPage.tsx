import { Stack, Table, Text, Title } from '@mantine/core'
import { useNavigate } from '@tanstack/react-router'

import { useCareer, useClubFixtures } from '../api/hooks'
import ClubLink from '../components/ClubLink'
import ResultBadge from '../components/ResultBadge'
import { longDate, score, stageLabel } from '../lib/format'

export default function FixturesPage() {
  const career = useCareer().data
  const fixtures = useClubFixtures(career?.club.id)
  const navigate = useNavigate()
  if (!career) return null
  return (
    <Stack>
      <Title order={2}>Fixtures & results</Title>
      <Table.ScrollContainer minWidth={700}>
        <Table highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Date</Table.Th>
              <Table.Th>Competition</Table.Th>
              <Table.Th>Venue</Table.Th>
              <Table.Th>Opponent</Table.Th>
              <Table.Th>Score</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {(fixtures.data ?? []).map((f) => {
              const home = f.home.id === career.club.id
              const opponent = home ? f.away : f.home
              const played = f.status === 'played'
              return (
                <Table.Tr
                  key={f.id}
                  style={{ cursor: played ? 'pointer' : undefined }}
                  onClick={() => played && void navigate({ to: '/match/$fixtureId', params: { fixtureId: String(f.id) } })}
                >
                  <Table.Td>{longDate(f.date)}</Table.Td>
                  <Table.Td>
                    <Text size="sm">{f.competition_name}</Text>
                    <Text size="xs" c="dimmed">
                      {stageLabel(f.stage, f.round, f.tie, f.leg)}
                    </Text>
                  </Table.Td>
                  <Table.Td>{f.neutral ? 'N' : home ? 'H' : 'A'}</Table.Td>
                  <Table.Td fw={500}>
                    <ClubLink club={opponent} />
                  </Table.Td>
                  <Table.Td>{played ? score(f) : '–'}</Table.Td>
                  <Table.Td>
                    <ResultBadge fixture={f} clubId={career.club.id} />
                  </Table.Td>
                </Table.Tr>
              )
            })}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Stack>
  )
}
