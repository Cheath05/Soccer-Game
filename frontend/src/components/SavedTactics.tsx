import { Alert, Button, Checkbox, Group, Menu, Modal, Stack, Text, TextInput } from '@mantine/core'
import { useState } from 'react'

import { useDeleteTacticPreset, useLoadTacticPreset, useSaveTacticPreset, useTacticPresets } from '../api/hooks'
import { shortDate } from '../lib/format'

/** The user's saved tactics: load one, save the tactic now under a name, or delete one. A saved
 * tactic is the formation, roles and instructions (and the line-up, if saved with it). */
export default function SavedTactics() {
  const presets = useTacticPresets()
  const save = useSaveTacticPreset()
  const load = useLoadTacticPreset()
  const remove = useDeleteTacticPreset()
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState('')
  const [withLineup, setWithLineup] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const list = presets.data ?? []

  const onSave = () =>
    void save.mutateAsync({ name, with_lineup: withLineup }).then(
      () => {
        setSaving(false)
        setNotice(`Saved “${name.trim()}”.`)
      },
      () => undefined,
    )

  return (
    <>
      <Menu position="bottom-end" withinPortal shadow="md" width={300}>
        <Menu.Target>
          <Button variant="default">Saved tactics{list.length ? ` (${list.length})` : ''}</Button>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item
            onClick={() => {
              setName('')
              setWithLineup(false)
              save.reset()
              setSaving(true)
            }}
          >
            Save this tactic…
          </Menu.Item>
          {list.length > 0 && <Menu.Divider />}
          {list.length > 0 && <Menu.Label>Load a saved tactic</Menu.Label>}
          {list.map((p) => (
            <Menu.Item
              key={p.id}
              closeMenuOnClick
              onClick={() =>
                void load.mutateAsync(p.id).then(
                  () => setNotice(`Loaded “${p.name}”.`),
                  (e: Error) => setNotice(e.message),
                )
              }
              rightSection={
                <Text
                  size="xs"
                  c="red"
                  role="button"
                  aria-label={`Delete ${p.name}`}
                  onClick={(ev) => {
                    ev.stopPropagation()
                    if (window.confirm(`Delete the saved tactic “${p.name}”?`)) void remove.mutateAsync(p.id)
                  }}
                >
                  Delete
                </Text>
              }
            >
              <Text size="sm" fw={500}>
                {p.name}
              </Text>
              <Text size="xs" c="dimmed">
                {p.formation}
                {p.with_lineup ? ' · with line-up' : ''} · {shortDate(p.saved)}
              </Text>
            </Menu.Item>
          ))}
        </Menu.Dropdown>
      </Menu>
      {notice && (
        <Text size="xs" c="dimmed" onClick={() => setNotice(null)}>
          {notice}
        </Text>
      )}
      <Modal opened={saving} onClose={() => setSaving(false)} title="Save this tactic">
        <Stack>
          <TextInput
            label="Name"
            placeholder="e.g. Press high, Park the bus"
            value={name}
            maxLength={40}
            onChange={(e) => setName(e.currentTarget.value)}
            data-autofocus
            onKeyDown={(e) => e.key === 'Enter' && name.trim() && onSave()}
          />
          <Checkbox
            label="Save the line-up too"
            description="Otherwise loading it keeps the formation, roles and instructions, and picks the best players."
            checked={withLineup}
            onChange={(e) => setWithLineup(e.currentTarget.checked)}
          />
          {list.some((p) => p.name === name.trim()) && (
            <Text size="xs" c="orange">
              This replaces the tactic saved as “{name.trim()}”.
            </Text>
          )}
          {save.error && <Alert color="red">{save.error.message}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setSaving(false)}>
              Cancel
            </Button>
            <Button disabled={!name.trim()} loading={save.isPending} onClick={onSave}>
              Save
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  )
}
