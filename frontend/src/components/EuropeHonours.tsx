import { Badge, Group, Paper, Stack, Text } from '@mantine/core'

import type { EuropeRun } from '../api/types'
import { EUROPE_COLOR } from '../lib/competitionColors'

/** One European run as a badge in its competition's colour; the winners' is solid. */
export function EuropeBadge({ run }: { run: EuropeRun }) {
  return (
    <Badge
      size="sm"
      variant={run.won ? 'filled' : 'light'}
      color={EUROPE_COLOR[run.key] ?? 'gray'}
      styles={{ root: { height: 'auto', padding: '2px 8px' }, label: { whiteSpace: 'normal' } }}
    >
      {run.short_name}: {run.reached}
    </Badge>
  )
}

/** The Treble: a gold banner with the three trophies, for a season (a club's history, the
 * season summary): the league, the cup, then the Champions League. `season` is left out where
 * the surrounding text gives it. */
export function TrebleBanner({ title, season, trophies }: { title: string; season?: string; trophies: string[] }) {
  return (
    <Paper
      p="sm"
      radius="md"
      aria-label="Treble"
      style={{
        background: 'linear-gradient(135deg, var(--mantine-color-yellow-3), var(--mantine-color-yellow-6))',
        border: '2px solid var(--mantine-color-yellow-8)',
        color: 'var(--mantine-color-dark-9)',
      }}
    >
      <Stack gap={6} align="center">
        <Text fw={800} size="xs" style={{ letterSpacing: '0.3em', textTransform: 'uppercase' }}>
          ★ Treble ★
        </Text>
        <Text fw={800} size="lg" ta="center" lh={1.2}>
          {title}
        </Text>
        {season && (
          <Text size="sm" fw={600}>
            {season}
          </Text>
        )}
        <Group gap={6} justify="center">
          {trophies.map((name, i) => (
            <Badge
              key={name}
              size="md"
              variant="filled"
              color={i === trophies.length - 1 ? EUROPE_COLOR.UCL : 'dark'}
              styles={{ root: { height: 'auto', padding: '3px 10px' }, label: { whiteSpace: 'normal' } }}
            >
              {name}
            </Badge>
          ))}
        </Group>
      </Stack>
    </Paper>
  )
}
