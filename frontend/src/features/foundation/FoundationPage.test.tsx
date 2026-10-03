import '@testing-library/jest-dom/vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { FoundationPage } from './FoundationPage'
import { AuthContext } from '../auth/authContextValue'

describe('FoundationPage', () => {
  it('presents the ticket core and its permission-aware navigation', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    render(
      <QueryClientProvider client={queryClient}>
        <AuthContext.Provider
          value={{
            user: {
              id: '73bb9477-5b69-4ee5-aacf-e80ed38a22520',
              email: 'operator@example.com',
              display_name: 'Operator',
              status: 'ACTIVE',
              roles: ['EMPLOYEE'],
              permissions: [
                'ticket:create',
                'ticket:view_own',
                'asset:view_own',
                'audit:view',
              ],
            },
            accessToken: 'token',
            loading: false,
            login: async () => {},
            logout: async () => {},
          }}
        >
          <MemoryRouter>
            <FoundationPage />
          </MemoryRouter>
        </AuthContext.Provider>
      </QueryClientProvider>,
    )
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'My support',
    )
    expect(screen.getByText('My open tickets')).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Create ticket' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /Ticket queue/ }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /Knowledge base/ }),
    ).toBeInTheDocument()
  })
})
