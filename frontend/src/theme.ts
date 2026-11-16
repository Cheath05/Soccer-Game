import { Badge, Button, Card, Modal, Paper, Table, Title, createTheme, type MantineColorsTuple } from '@mantine/core'

// The look of the game: dark, with one loud accent (an electric blue). The accent takes the place of Mantine's
// `teal`, which the pages already use for "good" (a fit player, a promotion place, Continue), so
// they all follow without naming a new colour.
const accent: MantineColorsTuple = [
  '#e9f3ff', '#d0e5ff', '#a3cbff', '#74b0ff', '#4f9bff', '#2f8cff', '#1f76e6', '#155fc0', '#0e4a98', '#083572',
]
// Mantine's dark scale, from text (0) to the deepest background (9): body is 7, cards and inputs
// 6, borders 4.
const dark: MantineColorsTuple = [
  '#e8edf3', '#c5ceda', '#8f9bab', '#5f6c7d', '#2a3644', '#1f2935', '#151c25', '#0b0f14', '#070a0e', '#040608',
]

export const HEADING_FONT = '"Barlow Condensed", "Arial Narrow", -apple-system, system-ui, sans-serif'

export const theme = createTheme({
  primaryColor: 'teal',
  primaryShade: { light: 5, dark: 5 },
  autoContrast: true, // white text on the accent
  colors: { teal: accent, dark },
  defaultRadius: 'md',
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  headings: {
    fontFamily: HEADING_FONT,
    fontWeight: '700',
    sizes: {
      h1: { fontSize: '2.4rem', lineHeight: '1.05' },
      h2: { fontSize: '1.9rem', lineHeight: '1.1' },
      h3: { fontSize: '1.5rem', lineHeight: '1.15' },
      h4: { fontSize: '1.25rem', lineHeight: '1.2' },
    },
  },
  components: {
    Card: Card.extend({ defaultProps: { radius: 'lg' } }),
    Paper: Paper.extend({ defaultProps: { radius: 'lg' } }),
    Modal: Modal.extend({ defaultProps: { radius: 'lg' } }),
    Button: Button.extend({ defaultProps: { radius: 'xl' }, styles: { label: { fontWeight: 700 } } }),
    Badge: Badge.extend({ defaultProps: { radius: 'sm' } }),
    Title: Title.extend({ styles: { root: { textTransform: 'uppercase', letterSpacing: '0.01em' } } }),
    Table: Table.extend({ defaultProps: { highlightOnHoverColor: 'var(--fs-surface-2)' } }),
  },
})
