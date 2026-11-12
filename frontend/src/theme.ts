import { Badge, Button, Card, Modal, Paper, Table, Title, createTheme, type MantineColorsTuple } from '@mantine/core'

// The look of the game: dark, with one loud accent. The accent takes the place of Mantine's
// `teal`, which the pages already use for "good" (a fit player, a promotion place, Continue), so
// they all follow without naming a new colour.
const accent: MantineColorsTuple = [
  '#f8ffe1', '#eefdbd', '#e2fb8f', '#d5f85f', '#cbf53e', '#c6f432', '#a9d51f', '#86ab14', '#63800c', '#425706',
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
  autoContrast: true, // dark text on the bright accent
  luminanceThreshold: 0.45,
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
