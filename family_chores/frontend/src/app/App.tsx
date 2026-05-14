import { HashRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { APIError } from '../api/client'
import { AppRoutes } from './routes'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { WebSocketProvider } from '../ws/provider'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      // Only retry transient server failures (5xx) — auth (401/403),
      // not-found (404), and validation (4xx) errors are deterministic,
      // so a retry just doubles the error count without recovering.
      retry: (failureCount, err) =>
        err instanceof APIError && err.status >= 500 ? failureCount < 1 : false,
      refetchOnWindowFocus: false,
    },
  },
})

export function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <HashRouter>
          <WebSocketProvider>
            <AppRoutes />
          </WebSocketProvider>
        </HashRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
