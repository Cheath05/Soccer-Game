import { Alert, Card, Stack, Text, Title } from '@mantine/core'

import { ApiError } from '../api/client'
import { useSetSimulation, useSimulation } from '../api/hooks'
import AutoTrainingSwitch from '../components/AutoTrainingSwitch'
import RecruitingAssistantSwitch from '../components/RecruitingAssistantSwitch'
import { useCareer } from '../api/hooks'
import OfferRulesCard from '../components/OfferRulesCard'
import SimulationPicker from '../components/SimulationPicker'

/** The career's settings: what bids for your players do while the game moves on, and which leagues
 * are fully simulated (the rest get fast results). */
export default function SettingsPage() {
  const sim = useSimulation()
  const save = useSetSimulation()
  const career = useCareer().data
  const college = !!career?.college
  // A national team's manager without a club has no players of his own to sell; his squad's
  // players train with him.
  const club = !career?.nation_only
  const nation = !!career?.nation || !!career?.nation_only
  return (
    <Stack>
      <Title order={2}>Settings</Title>
      {club && <OfferRulesCard />}
      {(club || nation) && (
        <Card withBorder padding="md">
          <Title order={4} mb="xs">
            Position training
          </Title>
          <Stack gap="sm">
            {club && <AutoTrainingSwitch />}
            {nation && <AutoTrainingSwitch team="nation" />}
          </Stack>
        </Card>
      )}
      {college && (
        <Card withBorder padding="md">
          <Title order={4} mb="xs">
            Recruiting
          </Title>
          <RecruitingAssistantSwitch />
        </Card>
      )}
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
