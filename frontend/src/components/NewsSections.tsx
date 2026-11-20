import { Accordion, Badge, Group, List, Text } from '@mantine/core'

import type { NewsSection } from '../api/types'

// The news after a Continue or a sim, in sections (api/news.py): your team first, then the
// conference champions a line each, college soccer, recruiting and the world beyond. The world's
// news starts folded away.

const FOLDED = ['Around the world']

export default function NewsSections({ sections, messages }: { sections?: NewsSection[]; messages: string[] }) {
  if (!sections || sections.length === 0) {
    return (
      <List spacing={4} size="sm">
        {messages.map((m, i) => (
          <List.Item key={`${i}-${m}`}>{m}</List.Item>
        ))}
      </List>
    )
  }
  const open = sections.map((s) => s.title).filter((t) => !FOLDED.includes(t) || sections.length === 1)
  return (
    <Accordion multiple variant="separated" defaultValue={open}>
      {sections.map((s) => (
        <Accordion.Item key={s.title} value={s.title}>
          <Accordion.Control>
            <Group gap="xs">
              <Text fw={600}>{s.title}</Text>
              <Badge size="sm" variant="light" color="gray">
                {s.items.length}
              </Badge>
            </Group>
          </Accordion.Control>
          <Accordion.Panel>
            <List spacing={4} size="sm">
              {s.items.map((m, i) => (
                <List.Item key={`${i}-${m}`}>{m}</List.Item>
              ))}
            </List>
          </Accordion.Panel>
        </Accordion.Item>
      ))}
    </Accordion>
  )
}
