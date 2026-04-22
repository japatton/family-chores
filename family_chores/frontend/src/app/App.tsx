import { HashRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AppRoutes } from './routes'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { WebSocketProvider } from '../ws/provider'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: 1,
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
