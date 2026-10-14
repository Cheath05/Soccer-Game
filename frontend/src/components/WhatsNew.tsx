import { Accordion, Alert, Badge, Button, Collapse, List, Loader, Modal, Paper, ScrollArea, Stack, Tabs, Text, TextInput } from '@mantine/core'
import { useMediaQuery } from '@mantine/hooks'
import { type ReactNode, useState } from 'react'

import { useChangelog } from '../api/hooks'
import type { ChangelogEntry } from '../api/types'
import { useDevice } from '../lib/device'
import { HELP_TOPICS, type HelpBlock, matchingTopics } from '../lib/help'

// What is above the list in the window: its title bar, the "You're on" line with its buttons and
// the tab bar. The list gets the rest of the window's height and scrolls inside it, so the tabs
// and the Copy version button stay in view. The build details, when open, take more room.
const CHROME = { phone: '13.5rem', computer: '14rem' }
const DETAILS = '5.5rem'
const SAFE = 'env(safe-area-inset-top) - env(safe-area-inset-bottom)'

function versionKey(version: string): [number, number] {
  const [major, minor] = version.split('.').map(Number)
  return [major || 0, minor || 0]
}

// Negative when `a` is the older version.
function compareVersions(a: string, b: string): number {
  const [a1, a2] = versionKey(a)
  const [b1, b2] = versionKey(b)
  return a1 - b1 || a2 - b2
}

// "14 Oct 2026" from an ISO date.
function day(iso: string): string {
  const date = new Date(`${iso}T12:00:00`)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

function Bullets({ items }: { items: string[] }) {
  return (
    <List size="sm" spacing={4}>
      {items.map((item) => (
        <List.Item key={item} style={{ overflowWrap: 'anywhere' }}>
          {item}
        </List.Item>
      ))}
    </List>
  )
}

function Entry({ entry, note, current }: { entry: ChangelogEntry; note: string | null; current: boolean }) {
  return (
    <Paper
      withBorder
      p="sm"
      radius="md"
      data-testid="changelog-entry"
      style={current ? { borderColor: 'var(--mantine-primary-color-filled)', borderWidth: 2 } : undefined}
    >
      <Stack gap={6}>
        <div>
          <Badge variant={current ? 'filled' : 'light'} radius="sm" size="lg" tt="none" mr="xs" style={{ verticalAlign: 'middle' }}>
            v{entry.version}
          </Badge>
          <Text span fw={600} style={{ verticalAlign: 'middle' }}>
            {entry.title}
          </Text>
          <Text span size="xs" c="dimmed" ml="xs" style={{ verticalAlign: 'middle', whiteSpace: 'nowrap' }}>
            {day(entry.date)}
          </Text>
        </div>
        {note && (
          <Text size="xs" fw={600} c={current ? 'teal' : 'dimmed'}>
            {note}
          </Text>
        )}
        <Bullets items={entry.changes} />
      </Stack>
    </Paper>
  )
}

// Every version, newest first. `version` is what the server is running ("1.53"), or null where it
// has no number: the entry for it is marked, or the newest one before it where it has none.
function Versions({ version, maxHeight }: { version: string | null; maxHeight: string | undefined }) {
  const changelog = useChangelog(true)
  if (changelog.isPending) return <Loader size="sm" />
  if (changelog.error || !changelog.data) {
    return <Alert color="red">The patch notes couldn&apos;t be loaded{changelog.error ? `: ${changelog.error.message}` : ''}.</Alert>
  }
  const running = version ?? (changelog.data.version !== 'unknown' ? changelog.data.version : null)
  const entries = changelog.data.entries
  const here = running ? entries.find((entry) => compareVersions(entry.version, running) <= 0) : undefined
  return (
    <ScrollArea.Autosize mah={maxHeight} type="auto" offsetScrollbars>
      <Stack gap="sm">
        <Text size="xs" c="dimmed">
          Newest first. A version that isn&apos;t listed changed nothing you&apos;d see in the game.
        </Text>
        {entries.map((entry) => {
          const newer = running !== null && compareVersions(entry.version, running) > 0
          const current = entry === here
          const note = current
            ? entry.version === running
              ? `You're on this version`
              : `The latest update you have (you're on v${running})`
            : newer
              ? 'Not on this server yet'
              : null
          return <Entry key={entry.version} entry={entry} note={note} current={current} />
        })}
      </Stack>
    </ScrollArea.Autosize>
  )
}

function Blocks({ blocks }: { blocks: HelpBlock[] }) {
  return (
    <Stack gap="xs">
      {blocks.map((block, i) =>
        typeof block === 'string' ? (
          <Text key={i} size="sm" style={{ overflowWrap: 'anywhere' }}>
            {block}
          </Text>
        ) : (
          <Bullets key={i} items={block} />
        ),
      )}
    </Stack>
  )
}

// What you can do in the game, a topic at a time, with a search box.
function Help({ maxHeight }: { maxHeight: string | undefined }) {
  const { touch } = useDevice()
  const [query, setQuery] = useState('')
  const topics = matchingTopics(HELP_TOPICS, query)
  const searching = query.trim() !== ''
  return (
    <Stack gap="xs">
      <TextInput
        type="search"
        placeholder="Search the help"
        aria-label="Search the help"
        size={touch ? 'md' : 'sm'}
        value={query}
        onChange={(event) => setQuery(event.currentTarget.value)}
      />
      <ScrollArea.Autosize mah={maxHeight && `calc(${maxHeight} - 3rem)`} type="auto" offsetScrollbars>
        {topics.length === 0 ? (
          <Text size="sm" c="dimmed">
            Nothing in the help matches &ldquo;{query.trim()}&rdquo;.
          </Text>
        ) : (
          // Remounted as the search changes, so a single match opens by itself.
          <Accordion key={searching ? query : 'all'} variant="separated" defaultValue={searching && topics.length === 1 ? topics[0].id : null}>
            {topics.map((topic) => (
              <Accordion.Item key={topic.id} value={topic.id}>
                <Accordion.Control>
                  <Text span display="block" fw={600} size="sm">
                    {topic.title}
                  </Text>
                  <Text span display="block" size="xs" c="dimmed">
                    {topic.summary}
                  </Text>
                </Accordion.Control>
                <Accordion.Panel>
                  <Blocks blocks={topic.blocks} />
                </Accordion.Panel>
              </Accordion.Item>
            ))}
          </Accordion>
        )}
      </ScrollArea.Autosize>
    </Stack>
  )
}

function Body({ heading, version, details, mismatch, copy, copied, scrolls }: Omit<Props, 'opened' | 'onClose'> & { scrolls: boolean }) {
  const { phone } = useDevice()
  const [tab, setTab] = useState<string | null>('new')
  const [showDetails, setShowDetails] = useState(false)
  // The part under the tab bar: the rest of the window, less what is above it. (On a screen too
  // short for that, the whole window scrolls instead.)
  const above = `${phone ? CHROME.phone : CHROME.computer}${showDetails ? ` - ${DETAILS}` : ''}`
  const maxHeight = !scrolls ? undefined : phone ? `calc(100dvh - ${above} - ${SAFE})` : `calc(90dvh - ${above})`
  return (
    <Stack gap="xs">
      <Stack gap={2}>
        <Text fw={600}>{heading}</Text>
        {mismatch && (
          <Text size="xs" c="orange">
            The page and the server are on different versions: reload the page.
          </Text>
        )}
        <div>
          <Button variant="default" size="compact-sm" mr="xs" onClick={copy}>
            {copied ? 'Copied' : 'Copy version'}
          </Button>
          <Button variant="subtle" color="gray" size="compact-sm" aria-expanded={showDetails} onClick={() => setShowDetails((open) => !open)}>
            {showDetails ? 'Hide build details' : 'Build details'}
          </Button>
        </div>
        <Collapse expanded={showDetails}>
          <Text component="div" size="xs" c="dimmed" pt={4}>
            {details}
          </Text>
        </Collapse>
      </Stack>
      <Tabs value={tab} onChange={setTab} keepMounted={false}>
        <Tabs.List grow>
          <Tabs.Tab value="new">What&apos;s new</Tabs.Tab>
          <Tabs.Tab value="help">Help</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="new" pt="sm">
          <Versions version={version} maxHeight={maxHeight} />
        </Tabs.Panel>
        <Tabs.Panel value="help" pt="sm">
          <Help maxHeight={maxHeight} />
        </Tabs.Panel>
      </Tabs>
    </Stack>
  )
}

interface Props {
  opened: boolean
  onClose: () => void
  /** Where the player is, in a line: "You're on v1.53 · 14 Oct". */
  heading: string
  /** The server's MAJOR.MINOR ("1.53") to match the entries against, or null where it has none. */
  version: string | null
  /** Branch, commit and build times: what the version tag's tooltip shows. */
  details: ReactNode
  /** The page and the server are on different commits. */
  mismatch: boolean
  /** Copies the line for a bug report. */
  copy: () => void
  copied: boolean
}

// Opened from the version tag: what changed in each version (the one the server runs marked), and
// help on what the game can do. The line to paste into a bug report is copied from here.
export default function WhatsNew({ opened, onClose, ...body }: Props) {
  const { phone } = useDevice()
  // A phone held on its side is wider than a phone but as short: it gets the whole screen too.
  const short = useMediaQuery('(max-height: 31.25em)', false, { getInitialValueInEffect: false })
  const full = phone || !!short
  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title="What's new and help"
      fullScreen={full}
      centered={!full}
      size="lg"
      closeButtonProps={{ 'aria-label': 'Close', size: full ? 44 : undefined }}
      // Clear of the notch and the home bar when the game is added to an iPhone's Home Screen.
      styles={{
        header: { paddingTop: 'calc(var(--mantine-spacing-md) + env(safe-area-inset-top))' },
        body: { paddingBottom: 'calc(var(--mantine-spacing-md) + env(safe-area-inset-bottom))' },
      }}
    >
      <Body {...body} scrolls={!short} />
    </Modal>
  )
}
