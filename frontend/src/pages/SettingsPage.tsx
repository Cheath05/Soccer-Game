import { Alert, Card, Stack, Text, Title } from '@mantine/core'

import { ApiError } from '../api/client'
import { useSetSimulation, useSimulation } from '../api/hooks'
import OfferRulesCard from '../components/OfferRulesCard'
import SimulationPicker from '../components/SimulationPicker'

/** The career's settings: what bids for your players do while the game moves on, and which leagues
 * are fully simulated (the rest get fast results). */
export default function SettingsPage() {
  const sim = useSimulation()
  const save = useSetSimulation()
  return (
    <Stack>
      <Title order={2}>Settings</Title>
      <OfferRulesCard />
      <Card withBorder padding="md">
        <Title order={4} mb={4}>
          Simulation
        </Title>
        <Text size="sm" c="dimmed" mb="sm">
          Changes apply from the next day played. Matches already played keep their results.
        </Text>
        {save.error && (
          <Alert color="red" variant="light" mb="sm">
            {save.error instanceof ApiError ? save.error.message : 'The setting couldn’t be saved.'}
          </Alert>
        )}
        {sim.data ? (
          <SimulationPicker fast={sim.data.fast} userLeague={sim.data.user_league} disabled={save.isPending} onChange={(fast) => save.mutate(fast)} />
        ) : (
          sim.error && <Text c="red">{sim.error.message}</Text>
        )}
      </Card>
    </Stack>
  )
}
