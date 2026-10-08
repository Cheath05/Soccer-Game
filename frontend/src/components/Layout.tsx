import { AppShell, Badge, Box, Burger, Button, Center, Group, List, Loader, Modal, NavLink, ScrollArea, Stack, Text, Title } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { Outlet, useNavigate, useRouterState } from '@tanstack/react-router'
import { useState } from 'react'

import { ApiError } from '../api/client'
import { useAdvance, useCareer, useSaveGame } from '../api/hooks'
import type { SeasonFinal } from '../api/types'
import { competitionNation, longDate, useCurrency } from '../lib/format'
import ClubSearch from './ClubSearch'
import SeasonSummary from './SeasonSummary'
import SimToDate from './SimToDate'
import VersionTag from './VersionTag'
import StartPage from '../pages/StartPage'

const NAV = [
  { to: '/', label: 'Dashboard' },
  { to: '/squad', label: 'Squad' },
  { to: '/tactics', label: 'Tactics' },
  { to: '/transfers', label: 'Transfers' },
  { to: '/finances', label: 'Finances' },
  { to: '/calendar', label: 'Calendar' },
  { to: '/fixtures', label: 'Fixtures' },
  { to: '/league', label: 'League' },
  { to: '/cups', label: 'Cups' },
  { to: '/start', label: 'Save / Load' },
] as const

export default function Layout() {
  const [opened, { toggle, close }] = useDisclosure()
  const career = useCareer()
  const advance = useAdvance()
  const saveGame = useSaveGame()
  const navigate = useNavigate()
  const path = useRouterState({ select: (s) => s.location.pathname })
  const currency = useCurrency() // pages re-render in a newly chosen currency
  const [messages, setMessages] = useState<string[]>([])
  // How the season went, when Continue ran on to its end.
  const [seasonFinal, setSeasonFinal] = useState<SeasonFinal | null>(null)
  const [saved, setSaved] = useState(false)

  if (career.isPending) {
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    )
  }
  const noCareer = career.error instanceof ApiError && career.error.status === 409
  if (noCareer || path === '/start' || !career.data) {
    return <StartPage hasCareer={!noCareer && !!career.data} error={noCareer ? null : career.error} />
  }

  const data = career.data
  const matchToday = data.next_fixture?.date === data.date

  const onContinue = () => {
    if (matchToday) {
      void navigate({ to: '/matchday' })
      return
    }
    advance.mutate(undefined, {
      onSuccess: (result) => {
        if (result.stop === 'season_end' && result.season_final) setSeasonFinal(result.season_final)
        else if (result.messages.length) setMessages(result.messages)
        if (result.stop === 'match') void navigate({ to: '/matchday' })
        if (result.stop === 'offer') void navigate({ to: '/transfers' })
      },
    })
  }

  return (
    <AppShell header={{ height: 60 }} navbar={{ width: 210, breakpoint: 'sm', collapsed: { mobile: !opened } }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <div>
              <Title order={4}>{data.club.name}</Title>
              {/* The navbar is folded away on a phone, so the version tag sits under the name there. */}
              <Box hiddenFrom="sm" maw={150}>
                <VersionTag truncate />
              </Box>
            </div>
            <Badge variant="light" visibleFrom="sm">
              {data.season}
            </Badge>
          </Group>
          <Group gap="sm" wrap="nowrap">
            <Box visibleFrom="md">
              <ClubSearch w={200} />
            </Box>
            <Text size="sm" fw={500} visibleFrom="xs">
              {longDate(data.date)}
            </Text>
            <Button
              variant="default"
              size="sm"
              loading={saveGame.isPending}
              onClick={() => saveGame.mutate(undefined, { onSuccess: () => { setSaved(true); setTimeout(() => setSaved(false), 1500) } })}
            >
              {saved ? 'Saved' : 'Save'}
            </Button>
            <SimToDate career={data} matchToday={matchToday} />
            <Button size="sm" color={matchToday ? 'orange' : 'teal'} loading={advance.isPending} onClick={onContinue}>
              {matchToday ? 'Match day' : 'Continue'}
            </Button>
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="sm">
        <Box hiddenFrom="md" mb="xs">
          <ClubSearch onPick={close} />
        </Box>
        {NAV.map((item) => (
          <div key={item.to}>
            {item.to === '/start' && data && (
              <NavLink
                label="Club & history"
                active={path === `/clubs/${data.club.id}`}
                onClick={() => {
                  close()
                  void navigate({ to: '/clubs/$clubId', params: { clubId: String(data.club.id) } })
                }}
              />
            )}
            <NavLink
              label={item.label}
              active={item.to === '/' ? path === '/' : path.startsWith(item.to)}
              onClick={() => {
                close()
                void navigate({ to: item.to })
              }}
            />
          </div>
        ))}
        {matchToday && (
          <NavLink label="Match day" color="orange" active={path === '/matchday'} onClick={() => void navigate({ to: '/matchday' })} />
        )}
        <AppShell.Section mt="auto" pt="sm" px="sm">
          <VersionTag />
        </AppShell.Section>
      </AppShell.Navbar>
      <AppShell.Main>
        {advance.error && (
          <Text c="red" mb="sm">
            {advance.error.message}
          </Text>
        )}
        <Outlet key={currency} />
      </AppShell.Main>
      <Modal
        opened={seasonFinal !== null}
        onClose={() => setSeasonFinal(null)}
        title="Season summary"
        centered
        size="lg"
        scrollAreaComponent={ScrollArea.Autosize}
      >
        {seasonFinal && (
          <Stack>
            <SeasonSummary
              final={seasonFinal}
              userClubId={data.club.id}
              userNation={data.competition ? competitionNation(data.competition) : undefined}
              onNavigate={() => setSeasonFinal(null)}
            />
            <Button onClick={() => setSeasonFinal(null)}>OK</Button>
          </Stack>
        )}
      </Modal>
      <Modal opened={messages.length > 0} onClose={() => setMessages([])} title="News" centered>
        <Stack>
          <List spacing="xs">
            {messages.map((m) => (
              <List.Item key={m}>{m}</List.Item>
            ))}
          </List>
          <Button onClick={() => setMessages([])}>OK</Button>
        </Stack>
      </Modal>
    </AppShell>
  )
}
