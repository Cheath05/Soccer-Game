import { Drawer, Stack } from '@mantine/core'
import type { ReactNode } from 'react'

// The phone's navigation: five tabs at the thumb, and a sheet for the rest of the pages.

const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' } as const
const icon = (children: ReactNode) => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...stroke}>
    {children}
  </svg>
)

const ICONS = {
  home: icon(<><path d="M4 11.5 12 4l8 7.5" /><path d="M6.5 10v9h11v-9" /><path d="M10 19v-5h4v5" /></>),
  squad: icon(<><circle cx="9" cy="8" r="3.2" /><path d="M3 19c.6-3.4 3-5 6-5s5.4 1.6 6 5" /><circle cx="17" cy="9" r="2.4" /><path d="M16.5 14.2c2.4.2 4 1.7 4.5 4.3" /></>),
  tactics: icon(<><rect x="3.5" y="4" width="17" height="16" rx="2" /><path d="M12 4v16" /><circle cx="12" cy="12" r="2.6" /><path d="M3.5 9.500h3v5h-3M20.5 9.500h-3v5h3" /></>),
  transfers: icon(<><path d="M4 8.500h13" /><path d="m14 5 3.5 3.500L14 12" /><path d="M20 15.500H7" /><path d="m10 12-3.5 3.500L10 19" /></>),
  more: icon(<><circle cx="5.5" cy="12" r="1.3" /><circle cx="12" cy="12" r="1.3" /><circle cx="18.5" cy="12" r="1.3" /></>),
  finances: icon(<><rect x="3.5" y="6" width="17" height="12" rx="2" /><circle cx="12" cy="12" r="2.5" /><path d="M7 9.500v5M17 9.500v5" /></>),
  calendar: icon(<><rect x="4" y="5.5" width="16" height="14.5" rx="2" /><path d="M4 10h16M8.5 3.500v4M15.5 3.500v4" /></>),
  fixtures: icon(<><path d="M5 6.500h14M5 12h14M5 17.500h9" /></>),
  league: icon(<><path d="M5 20V10M12 20V4M19 20v-7" /></>),
  cups: icon(<><path d="M8 4h8v5a4 4 0 0 1-8 0z" /><path d="M8 6H5c0 3 1.5 4.5 3.5 4.500M16 6h3c0 3-1.5 4.5-3.5 4.5" /><path d="M12 13v4M8.5 20h7M9.5 17h5" /></>),
  europe: icon(<><circle cx="12" cy="12" r="8" /><path d="M4 12h16M12 4c2.5 2.5 2.5 13.5 0 16M12 4c-2.5 2.5-2.5 13.5 0 16" /></>),
  club: icon(<><path d="M12 3.5 19 6v5.500c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z" /><path d="M9.5 12 11.5 14l3.5-4" /></>),
  saves: icon(<><path d="M5 4.500h11l3 3V19.500H5z" /><path d="M8 4.500v5h7v-5M8 19.500v-6h8v6" /></>),
  matchday: icon(<><circle cx="12" cy="12" r="8" /><path d="m12 8 3.2 2.3-1.2 3.700h-4l-1.2-3.700z" /></>),
} as const

export type NavIcon = keyof typeof ICONS

export interface NavItem {
  to: string
  label: string
  icon: NavIcon
  active: boolean
}

export function TabBar({ items, moreActive, onPick, onMore }: {
  items: NavItem[]
  moreActive: boolean
  onPick: (to: string) => void
  onMore: () => void
}) {
  return (
    <nav className="fs-tabbar" aria-label="Main">
      {items.map((item) => (
        <button
          key={item.to}
          type="button"
          className="fs-tab"
          data-active={item.active || undefined}
          data-matchday={item.icon === 'matchday' || undefined}
          aria-current={item.active ? 'page' : undefined}
          onClick={() => onPick(item.to)}
        >
          {ICONS[item.icon]}
          {item.label}
        </button>
      ))}
      <button type="button" className="fs-tab" data-active={moreActive || undefined} onClick={onMore}>
        {ICONS.more}
        More
      </button>
    </nav>
  )
}

export function MoreSheet({ opened, onClose, items, onPick, header, footer }: {
  opened: boolean
  onClose: () => void
  items: NavItem[]
  onPick: (to: string) => void
  header?: ReactNode
  footer?: ReactNode
}) {
  return (
    <Drawer
      opened={opened}
      onClose={onClose}
      position="bottom"
      size="auto"
      title="More"
      radius="lg"
      styles={{
        inner: { alignItems: 'flex-end' },
        content: { height: 'auto', maxHeight: '85dvh', borderBottomLeftRadius: 0, borderBottomRightRadius: 0, background: 'var(--fs-surface)' },
        header: { background: 'var(--fs-surface)' },
        title: { fontFamily: 'var(--fs-heading)', fontWeight: 700, fontSize: '1.4rem', textTransform: 'uppercase' },
        body: { paddingBottom: 'calc(16px + env(safe-area-inset-bottom))' },
      }}
    >
      <Stack gap="md">
        {header}
        <div className="fs-more-grid">
          {items.map((item) => (
            <button
              key={item.to}
              type="button"
              className="fs-more-item"
              data-active={item.active || undefined}
              onClick={() => onPick(item.to)}
            >
              {ICONS[item.icon]}
              {item.label}
            </button>
          ))}
        </div>
        {footer}
      </Stack>
    </Drawer>
  )
}

/** A club's initials on a disc, where a crest would be. */
export function Crest({ name, size = 36, mine = false }: { name: string; size?: number; mine?: boolean }) {
  const words = name.replace(/\b(FC|AFC|CF|SC|CD|AC|AS|SV|FK|IF|BK)\b\.?/g, '').trim().split(/\s+/).filter(Boolean)
  const initials = (words.length >= 2 ? words[0][0] + words[1][0] : (words[0] ?? name).slice(0, 2)).toUpperCase()
  return (
    <span className="fs-crest" data-mine={mine || undefined} style={{ width: size, height: size, fontSize: size * 0.42 }} aria-hidden="true">
      {initials}
    </span>
  )
}
