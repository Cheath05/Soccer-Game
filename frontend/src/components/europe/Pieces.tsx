import { Group, Text } from '@mantine/core'
import { Link } from '@tanstack/react-router'
import type { ReactNode } from 'react'

import type { Career, Fixture } from '../../api/types'
import { fixtureTarget } from './shared'

const linkStyle = { color: 'inherit', textDecoration: 'none' }

/** A fixture's score as a link (see `fixtureTarget`); plain text when it leads nowhere. The click
 * stays on the link, so it also works inside rows that open the same place. */
export function FixtureLink({ fixture, career, children }: { fixture: Fixture; career: Career | undefined; children: ReactNode }) {
  const target = fixtureTarget(fixture, career)
  const hover = {
    onMouseEnter: (e: React.MouseEvent<HTMLAnchorElement>) => (e.currentTarget.style.textDecoration = 'underline'),
    onMouseLeave: (e: React.MouseEvent<HTMLAnchorElement>) => (e.currentTarget.style.textDecoration = 'none'),
    onClick: (e: React.MouseEvent) => e.stopPropagation(),
    style: linkStyle,
  }
  if (target === 'report') {
    return (
      <Link to="/match/$fixtureId" params={{ fixtureId: String(fixture.id) }} {...hover}>
        {children}
      </Link>
    )
  }
  if (target === 'matchday') {
    return (
      <Link to="/matchday" {...hover}>
        {children}
      </Link>
    )
  }
  return <>{children}</>
}

/** A little coloured square with a label, for a legend. */
export function Swatch({ color, label }: { color: string; label: string }) {
  return (
    <Group gap={4} wrap="nowrap">
      <div
        style={{
          width: 14,
          height: 14,
          background: `var(--mantine-color-${color}-light)`,
          boxShadow: `inset 3px 0 0 var(--mantine-color-${color}-6)`,
          borderRadius: 3,
        }}
      />
      <Text size="xs">{label}</Text>
    </Group>
  )
}
