import { Box, Card, Group, SimpleGrid, Stack, Text, Title } from '@mantine/core'

import type { Career, CupRound } from '../../api/types'
import { useDevice } from '../../lib/device'
import { dateList } from './shared'
import TieCard from './TieCard'

function Dates({ round }: { round: CupRound }) {
  return (
    <Text size="xs" c="dimmed">
      {dateList(round.dates)}
      {round.legs === 2 ? ' · two legs' : ' · one match'}
    </Text>
  )
}

/** The knockout rounds: on a computer a bracket, a column per round, from the play-off to the
 * final; on a phone the rounds one under another, the latest first and those still to come
 * together at the end. */
export default function Knockouts({ rounds, userId, career }: { rounds: CupRound[]; userId: number | undefined; career: Career | undefined }) {
  const { phone } = useDevice()
  if (phone) {
    const drawn = rounds.filter((r) => r.drawn).reverse()
    const toCome = rounds.filter((r) => !r.drawn)
    return (
      <Stack gap="sm">
        {drawn.map((round) => (
          <Card key={round.index} withBorder padding="sm" aria-label={round.name}>
            <Title order={5}>{round.name}</Title>
            <Dates round={round} />
            <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="xs" mt="xs">
              {round.ties.map((t) => (
                <TieCard key={t.tie} tie={t} legs={round.legs} userId={userId} career={career} />
              ))}
            </SimpleGrid>
          </Card>
        ))}
        {toCome.length > 0 && (
          <Card withBorder padding="sm">
            <Text fw={600} mb={4}>
              {drawn.length ? 'Still to come' : 'Not drawn yet'}
            </Text>
            {toCome.map((r) => (
              <Text key={r.index} size="sm" c="dimmed">
                {r.name} · {dateList(r.dates)}
              </Text>
            ))}
          </Card>
        )}
      </Stack>
    )
  }
  return (
    <Box style={{ overflowX: 'auto' }} pb="xs">
      <Group align="stretch" wrap="nowrap" gap={12} style={{ minWidth: 'min-content' }}>
        {rounds.map((round) => (
          <Stack key={round.index} gap="xs" style={{ flex: '1 1 214px', minWidth: 214, maxWidth: 300 }} aria-label={round.name}>
            <div>
              <Text fw={600}>{round.name}</Text>
              <Dates round={round} />
            </div>
            <Stack gap="xs" justify={round.drawn ? 'space-around' : 'flex-start'} style={{ flex: 1 }}>
              {round.drawn ? (
                round.ties.map((t) => <TieCard key={t.tie} tie={t} legs={round.legs} userId={userId} career={career} />)
              ) : (
                <Card withBorder padding="sm">
                  <Text size="sm" c="dimmed" ta="center">
                    Not drawn yet
                  </Text>
                </Card>
              )}
            </Stack>
          </Stack>
        ))}
      </Group>
    </Box>
  )
}
