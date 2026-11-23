import { Button, Card, Group, Stack, Text, Title } from '@mantine/core'
import { Link } from '@tanstack/react-router'

import type { PastFinal } from '../api/types'
import ClubLink from './ClubLink'

/** Every past final of a cup (GET /international/history), latest first: the champion, the
 * runner-up, the score and the hosts. "View" opens that edition. Nothing before the first. */
export default function PastFinals({ title, finals, onView }: { title: string; finals: PastFinal[]; onView: (year: number) => void }) {
  if (finals.length === 0) return null
  return (
    <Card withBorder padding="sm" aria-label={title}>
      <Title order={4} mb="xs">
        {title}
      </Title>
      <Stack gap={8}>
        {finals.map((f) => (
          <Group key={f.year} justify="space-between" wrap="nowrap" align="flex-start" className="fs-row">
            <div style={{ minWidth: 0 }}>
              <Text size="sm" fw={700}>
                {f.year}{' '}
                <Text span fw={700}>
                  <ClubLink club={f.champion} />
                </Text>
              </Text>
              <Text size="xs" c="dimmed">
                Beat <ClubLink club={f.runner_up} /> in the final,{' '}
                <Link to="/match/$fixtureId" params={{ fixtureId: String(f.fixture_id) }}>
                  {f.score}
                </Link>
                {f.third ? ` · third: ${f.third.name}` : ''} · hosted by {f.hosts.join(', ')}
              </Text>
            </div>
            <Button size="compact-xs" variant="default" onClick={() => onView(f.year)}>
              View
            </Button>
          </Group>
        ))}
      </Stack>
    </Card>
  )
}
