import { Button, Card, Center, Loader, PasswordInput, Stack, Text, TextInput, Title } from '@mantine/core'
import { type QueryClient, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, type ReactNode, useEffect, useState } from 'react'

import { ApiError, SIGNED_OUT, api } from '../api/client'

export interface Me {
  auth: boolean // whether this server asks for accounts at all
  name: string | null
  is_owner: boolean
}

export const useMe = () => useQuery({ queryKey: ['me'], queryFn: () => api.get<Me>('/auth/me'), staleTime: Infinity, retry: 1 })

// Everything else waits until someone is signed in, when the server has accounts (FOOTSIM_AUTH).
// Without accounts it shows the game straight away, as before.
export default function AuthGate({ children }: { children: ReactNode }) {
  const me = useMe()
  const queryClient = useQueryClient()

  useEffect(() => {
    const signedOut = () => void queryClient.invalidateQueries({ queryKey: ['me'] })
    window.addEventListener(SIGNED_OUT, signedOut)
    return () => window.removeEventListener(SIGNED_OUT, signedOut)
  }, [queryClient])

  if (me.isPending) {
    return (
      <Center h="100dvh">
        <Loader />
      </Center>
    )
  }
  if (me.data?.auth && !me.data.name) return <SignIn />
  return <>{children}</>
}

// Nothing cached for whoever used this browser before may show to the next player. ['me'] stays:
// the gate is watching it (clearing it too would leave the gate on a query that's gone).
function forgetOthers(queryClient: QueryClient) {
  queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'me' })
}

function SignIn() {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const me = await api.post<Me>('/auth/login', { name: name.trim(), password })
      forgetOthers(queryClient)
      queryClient.setQueryData(['me'], me)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not reach the server')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Center mih="100dvh" p="md">
      <Card withBorder shadow="sm" w="100%" maw={360} p="lg">
        <form onSubmit={(e) => void submit(e)}>
          <Stack>
            <Title order={3}>footsim</Title>
            <Text size="sm" c="dimmed">
              Sign in to play your own careers.
            </Text>
            <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} autoComplete="username" autoCapitalize="none" autoCorrect="off" required size="md" />
            <PasswordInput label="Password" value={password} onChange={(e) => setPassword(e.currentTarget.value)} autoComplete="current-password" required size="md" />
            {error && (
              <Text c="red" size="sm">
                {error}
              </Text>
            )}
            <Button type="submit" loading={busy} size="md">
              Sign in
            </Button>
            <Text size="xs" c="dimmed">
              No account? Ask whoever runs this server to make you one.
            </Text>
          </Stack>
        </form>
      </Card>
    </Center>
  )
}

// Who is signed in, and Sign out: shown at the foot of the menu when the server has accounts.
export function AccountFooter() {
  const me = useMe().data
  const queryClient = useQueryClient()
  if (!me?.auth || !me.name) return null
  const signOut = async () => {
    await api.post('/auth/logout').catch(() => undefined)
    forgetOthers(queryClient)
    queryClient.setQueryData(['me'], { auth: true, name: null, is_owner: false })
  }
  return (
    <Stack gap={4} mb="xs">
      <Text size="xs" c="dimmed" truncate>
        Signed in as {me.name}
      </Text>
      <Button variant="subtle" size="compact-sm" color="gray" onClick={() => void signOut()} justify="start" px={0}>
        Sign out
      </Button>
    </Stack>
  )
}
