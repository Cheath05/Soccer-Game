import '@mantine/core/styles.css'
import '@fontsource/barlow-condensed/600.css'
import '@fontsource/barlow-condensed/700.css'
import './app.css'

import { MantineProvider } from '@mantine/core'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from './App.tsx'
import AuthGate from './components/AuthGate'
import { theme } from './theme'

const queryClient = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MantineProvider theme={theme} forceColorScheme="dark">
      <QueryClientProvider client={queryClient}>
        <AuthGate>
          <App />
        </AuthGate>
      </QueryClientProvider>
    </MantineProvider>
  </StrictMode>,
)
