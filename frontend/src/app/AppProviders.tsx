import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { type PropsWithChildren, useState } from 'react'
import { BrowserRouter } from 'react-router-dom'
import { AppErrorBoundary } from './AppErrorBoundary'
import { AuthProvider } from '../features/auth/AuthContext'
import { RealtimeProvider } from '../features/realtime/RealtimeProvider'

export function AppProviders({ children }: PropsWithChildren) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: 1, staleTime: 30_000, refetchOnWindowFocus: false },
        },
      }),
  )
  return (
    <AppErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AuthProvider>
            <RealtimeProvider>{children}</RealtimeProvider>
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </AppErrorBoundary>
  )
}
