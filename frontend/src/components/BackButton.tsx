import { Button } from '@mantine/core'
import { useNavigate, useRouter } from '@tanstack/react-router'

/** Browser-history Back for pages reached by clicking in content; goes to `fallback` when there is no history to go back to. */
export default function BackButton({ fallback = '/' }: { fallback?: string }) {
  const router = useRouter()
  const navigate = useNavigate()
  const back = () => (window.history.length > 1 ? router.history.back() : void navigate({ to: fallback as never }))
  return (
    <Button variant="subtle" size="compact-sm" onClick={back}>
      ← Back
    </Button>
  )
}
