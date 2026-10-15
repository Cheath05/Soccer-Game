import { Badge, Box, Group, SimpleGrid, Stack, Text } from '@mantine/core'
import type { CSSProperties, ReactNode } from 'react'

import type { Career } from '../../api/types'
import { aggregate, feedsText, r16Of, SHORT } from './bracketModel'
import type { BNode, BracketModel } from './bracketModel'
import { dateList, dayDate } from './shared'
import TieCard from './TieCard'

function Card({
  node,
  userId,
  open,
  onToggle,
  footer,
}: {
  node: BNode
  userId: number | undefined
  open: boolean
  onToggle: (id: string) => void
  footer?: ReactNode
}) {
  const tie = node.tie
  const mine = userId !== undefined && (node.a.club?.id === userId || node.b.club?.id === userId)
  const winnerId = tie?.winner?.id
  const next = tie && !tie.winner ? tie.fixtures.find((f) => f.status !== 'played') : undefined
  const clickable = tie !== null
  return (
    <Box
      p={5}
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      aria-expanded={clickable ? open : undefined}
      aria-label={`${node.title}: ${node.a.label} v ${node.b.label}`}
      onClick={clickable ? () => onToggle(node.id) : undefined}
      onKeyDown={clickable ? (e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onToggle(node.id)) : undefined}
      style={{
        border: `1px solid ${mine ? 'var(--mantine-primary-color-filled)' : 'var(--mantine-color-default-border)'}`,
        borderStyle: tie ? 'solid' : 'dashed',
        borderRadius: 'var(--mantine-radius-md)',
        background: mine ? 'var(--mantine-primary-color-light)' : 'var(--mantine-color-body)',
        cursor: clickable ? 'pointer' : undefined,
        outline: open ? '2px solid var(--mantine-primary-color-filled)' : undefined,
        outlineOffset: 1,
      }}
    >
      <Text style={{ fontSize: 10, lineHeight: 1.2, letterSpacing: 0.4 }} c="dimmed" tt="uppercase">
        {node.title}
      </Text>
      {[node.a, node.b].map((slot, i) => {
        const won = slot.club !== null && slot.club.id === winnerId
        const lost = slot.club !== null && winnerId !== undefined && !won
        const total = aggregate(tie, slot.club)
        return (
          <div key={i} style={{ display: 'grid', gridTemplateColumns: '12px minmax(0, 1fr) auto', alignItems: 'center', columnGap: 3, minHeight: 22 }}>
            <Text size="xs" c="dimmed" ta="right">
              {slot.seed ?? ''}
            </Text>
            {slot.club ? (
              <Text truncate title={slot.club.name} style={{ fontSize: 13 }} fw={won || slot.club.id === userId ? 700 : undefined} c={lost ? 'dimmed' : undefined}>
                {slot.club.name}
              </Text>
            ) : (
              <Text size="xs" c="dimmed" fs="italic" lineClamp={2} lh={1.2} title={slot.label}>
                {slot.label}
              </Text>
            )}
            <Text size="sm" fw={700} ta="right" c={lost ? 'dimmed' : undefined} style={{ minWidth: 12 }}>
              {total ?? ''}
            </Text>
          </div>
        )
      })}
      {next && (
        <Text size="xs" c="dimmed">
          Next: {dayDate(next.date)}
        </Text>
      )}
      {footer && (
        <Text size="xs" c="dimmed" lh={1.25} mt={2}>
          {footer}
        </Text>
      )}
    </Box>
  )
}

function RoundHead({ model, round }: { model: BracketModel; round: number }) {
  const info = model.info[round]
  return (
    <div>
      <Text fw={600} size="sm" lh={1.2}>
        {info?.name ?? SHORT[round]}
      </Text>
      {info && (
        <Text size="xs" c="dimmed" lh={1.25}>
          {dateList(info.dates)}
          {info.legs === 2 ? ' · two legs' : ' · one match'}
        </Text>
      )}
      {info && !info.drawn && (
        <Text size="xs" c="dimmed" fs="italic" lh={1.25}>
          Not drawn yet
        </Text>
      )}
    </div>
  )
}

const GAP = 18
const LINE = 'var(--mantine-color-default-border)'

/** The lines from a tie to the one it feeds: a stub, the bar joining it to its pair, and the
 * stub out to the next card. A semi-final just runs straight across to the final. */
function Connector({ side, role }: { side: 'L' | 'R'; role: 'top' | 'bottom' | 'straight' }) {
  const line: CSSProperties = { position: 'absolute', background: LINE }
  const near = side === 'L' ? { left: 0 } : { right: 0 }
  const far = side === 'L' ? { right: 0 } : { left: 0 }
  const mid = side === 'L' ? { left: GAP / 2 - 1 } : { right: GAP / 2 - 1 }
  return (
    <div aria-hidden style={{ position: 'absolute', top: 0, bottom: 0, width: GAP, [side === 'L' ? 'left' : 'right']: '100%', pointerEvents: 'none' }}>
      {role === 'straight' ? (
        <div style={{ ...line, top: 'calc(50% - 1px)', height: 2, left: 0, right: 0 }} />
      ) : (
        <>
          <div style={{ ...line, ...near, top: 'calc(50% - 1px)', height: 2, width: GAP / 2 }} />
          <div style={{ ...line, ...mid, width: 2, top: role === 'top' ? '50%' : 0, bottom: role === 'top' ? 0 : '50%' }} />
          <div style={{ ...line, ...far, height: 2, width: GAP / 2, [role === 'top' ? 'bottom' : 'top']: -1 }} />
        </>
      )}
    </div>
  )
}

/** The play-off ties, in the order of the round-of-16 ties they feed. */
function Playoff({ model, userId, cols, selected, onSelect, inline, career }: ViewProps & { cols: number; inline: boolean }) {
  const ties = [...(model.nodes[0] ?? [])].sort((x, y) => r16Of(model, x) - r16Of(model, y))
  return (
    <Stack gap="xs">
      <RoundHead model={model} round={0} />
      <SimpleGrid cols={cols} spacing="xs">
        {ties.map((n) => (
          <div key={n.id}>
            <Card node={n} userId={userId} open={selected === n.id} onToggle={onSelect} footer={feedsText(model, n)} />
            {inline && selected === n.id && n.tie && <Legs node={n} model={model} userId={userId} career={career} />}
          </div>
        ))}
      </SimpleGrid>
    </Stack>
  )
}

function Legs({ node, model, userId, career }: { node: BNode; model: BracketModel; userId: number | undefined; career: Career | undefined }) {
  if (!node.tie) return null
  return (
    <Box mt={4}>
      <TieCard tie={node.tie} legs={model.info[node.round]?.legs ?? 2} userId={userId} career={career} />
    </Box>
  )
}

export interface ViewProps {
  model: BracketModel
  userId: number | undefined
  career: Career | undefined
  selected: string | null
  onSelect: (id: string) => void
}

/** On a computer: the play-off as a block of feeders over a bracket whose two halves meet in the
 * final in the middle. Clicking a tie shows its legs under the bracket. */
export function BracketDesktop(props: ViewProps) {
  const { model, userId, selected, onSelect, career } = props
  const nr16 = model.nodes[1]?.length ?? 8
  const rows = Math.max(1, nr16 / 2)
  const cells: ReactNode[] = []
  const heads: ReactNode[] = []
  // columns 1..7: R16, QF, SF (top half), final, SF, QF, R16 (bottom half)
  const layout: { round: number; col: number; side: 'L' | 'R' | null; half: 0 | 1 | null }[] = [
    { round: 1, col: 1, side: 'L', half: 0 },
    { round: 2, col: 2, side: 'L', half: 0 },
    { round: 3, col: 3, side: 'L', half: 0 },
    { round: 4, col: 4, side: null, half: null },
    { round: 3, col: 5, side: 'R', half: 1 },
    { round: 2, col: 6, side: 'R', half: 1 },
    { round: 1, col: 7, side: 'R', half: 1 },
  ]
  for (const { round, col, side, half } of layout) {
    heads.push(
      <div key={`h${col}`} style={{ gridColumn: col, gridRow: 1, paddingBottom: 4 }}>
        <RoundHead model={model} round={round} />
        {round === 1 && half !== null && (
          <Badge size="xs" variant="light" color="gray" mt={2}>
            {half === 0 ? 'Top half' : 'Bottom half'}
          </Badge>
        )}
      </div>,
    )
    const all = model.nodes[round] ?? []
    const perHalf = half === null ? all.length : all.length / 2
    const span = rows / perHalf
    all.forEach((n, idx) => {
      if (half !== null && Math.floor(idx / perHalf) !== half) return
      const i = half === null ? 0 : idx % perHalf
      const role = side === null ? null : perHalf === 1 ? 'straight' : i % 2 === 0 ? 'top' : 'bottom'
      cells.push(
        <div
          key={n.id}
          style={{ gridColumn: col, gridRow: `${2 + i * span} / span ${span}`, position: 'relative', display: 'flex', alignItems: 'center', padding: '4px 0' }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <Card node={n} userId={userId} open={selected === n.id} onToggle={onSelect} />
          </div>
          {side && role && <Connector side={side} role={role} />}
        </div>,
      )
    })
  }
  const chosen = selected ? model.nodes.flat().find((n) => n.id === selected) : undefined
  return (
    <Stack gap="md">
      <Playoff {...props} cols={4} inline={false} />
      <Box style={{ overflowX: 'auto' }} pb="xs">
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(7, minmax(140px, 1fr))',
            gridTemplateRows: `auto repeat(${rows}, minmax(80px, auto))`,
            columnGap: GAP,
            minWidth: 7 * 140 + 6 * GAP,
          }}
        >
          {heads}
          {cells}
        </div>
      </Box>
      {chosen?.tie && (
        <Box maw={380}>
          <Text size="sm" fw={600} mb={4}>
            {model.info[chosen.round]?.name ?? SHORT[chosen.round]}: {chosen.a.label} v {chosen.b.label}
          </Text>
          <Legs node={chosen} model={model} userId={userId} career={career} />
        </Box>
      )}
    </Stack>
  )
}

/** On a phone: the rounds one under another, each tie saying who its winner plays next. The two
 * halves are labelled; a tie opens to show its legs. */
export function BracketPhone(props: ViewProps) {
  const { model, userId, selected, onSelect, career } = props
  return (
    <Stack gap="md">
      <Playoff {...props} cols={1} inline />
      {[1, 2, 3, 4].map((round) => {
        const all = model.nodes[round] ?? []
        const half = all.length / 2
        return (
          <Stack key={round} gap="xs" aria-label={model.info[round]?.name}>
            <RoundHead model={model} round={round} />
            {all.map((n, idx) => (
              <div key={n.id}>
                {round <= 2 && half >= 1 && (idx === 0 || idx === half) && (
                  <Text size="xs" c="dimmed" fw={600} mb={4} mt={idx === 0 ? 0 : 6}>
                    {idx === 0 ? 'Top half of the bracket' : 'Bottom half of the bracket'}
                  </Text>
                )}
                <Card node={n} userId={userId} open={selected === n.id} onToggle={onSelect} footer={feedsText(model, n)} />
                {selected === n.id && n.tie && <Legs node={n} model={model} userId={userId} career={career} />}
              </div>
            ))}
          </Stack>
        )
      })}
    </Stack>
  )
}

export function PathLine({ path }: { path: string[] }) {
  if (!path.length) return null
  return (
    <Group gap={6} mb="xs" align="baseline">
      <Text size="xs" fw={700}>
        Your path
      </Text>
      <Text size="xs" c="dimmed">
        {path.join('  →  ')}
      </Text>
    </Group>
  )
}
