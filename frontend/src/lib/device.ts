import { useMediaQuery } from '@mantine/hooks'

// The single place the app decides "phone" versus "computer". `phone` follows the viewport width
// (below Mantine's `sm` breakpoint, 48em, the same one AppShell uses to fold the menu away);
// `touch` follows the primary pointer. Never sniff the user agent.
export function useDevice(): { phone: boolean; touch: boolean } {
  // getInitialValueInEffect: false reads the real value on the first render, so a phone never
  // flashes the computer layout.
  const phone = useMediaQuery('(max-width: 47.99em)', false, { getInitialValueInEffect: false })
  const touch = useMediaQuery('(pointer: coarse)', false, { getInitialValueInEffect: false })
  return { phone: !!phone, touch: !!touch }
}
