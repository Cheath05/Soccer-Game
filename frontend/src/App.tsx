import { Badge, Container, Group, Text, Title } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'

interface Health {
  status: string
  version: string
}

async function fetchHealth(): Promise<Health> {
  const response = await fetch('/api/health')
  if (!response.ok) throw new Error(`Backend returned ${response.status}`)
  return response.json() as Promise<Health>
}

export default function App() {
  const health = useQuery({ queryKey: ['health'], queryFn: fetchHealth })

  return (
    <Container size="md" py="xl">
      <Title order={1}>Footsim</Title>
      <Group mt="md">
        <Text>Backend:</Text>
        {health.isPending && <Badge color="gray">connecting</Badge>}
        {health.isError && <Badge color="red">offline</Badge>}
        {health.data && <Badge color="green">v{health.data.version}</Badge>}
      </Group>
    </Container>
  )
}
