import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { AuthContext } from '../auth/authContextValue'
import { AccessPage } from './AccessPage'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})
function setup() {
  render(
    <AuthContext.Provider
      value={{
        user: {
          id: 'a135c9eb-6ae3-467c-a4d0-6ff1ad19459c',
          email: 'admin@example.com',
          display_name: 'Admin',
          status: 'ACTIVE',
          roles: ['ADMIN'],
          permissions: ['role:view', 'role:manage'],
        },
        accessToken: 'signed-token',
        loading: false,
        login: async () => {},
        logout: async () => {},
      }}
    >
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <MemoryRouter>
          <AccessPage />
        </MemoryRouter>
      </QueryClientProvider>
    </AuthContext.Provider>,
  )
}
it('loads a user, saves explicit roles with a reason, and reports success', async () => {
  const calls: RequestInit[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit) => {
      if (init.method === 'PUT') {
        calls.push(init)
        return new Response(JSON.stringify(['EMPLOYEE']), { status: 200 })
      }
      if (url.includes('/users/'))
        return new Response(
          JSON.stringify({ roles: ['ADMIN'], permissions: [] }),
          { status: 200 },
        )
      return new Response(
        JSON.stringify([
          { code: 'EMPLOYEE', permissions: ['ticket:view_own'] },
          { code: 'ADMIN', permissions: ['role:manage'] },
        ]),
        { status: 200 },
      )
    }),
  )
  setup()
  const visitor = userEvent.setup()
  await screen.findByText('ADMIN', { selector: 'h2' })
  await visitor.type(
    screen.getByLabelText('User ID'),
    'cef11452-d5b6-4f1d-a982-31e7012a6ff2',
  )
  await visitor.click(screen.getByRole('button', { name: 'Load assignments' }))
  await visitor.click(await screen.findByRole('checkbox', { name: 'ADMIN' }))
  await visitor.click(screen.getByRole('checkbox', { name: 'EMPLOYEE' }))
  await visitor.type(
    screen.getByLabelText('Reason for change'),
    'Moved to employee support',
  )
  await visitor.click(screen.getByRole('button', { name: 'Save roles' }))
  await screen.findByText(/Role assignments saved/)
  expect(JSON.parse(String(calls[0].body))).toEqual({
    roles: ['EMPLOYEE'],
    reason: 'Moved to employee support',
  })
})
it('shows a backend permission denial instead of displaying empty roles', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(JSON.stringify({ title: 'Permission denied' }), {
          status: 403,
        }),
    ),
  )
  setup()
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Permission denied',
  )
})
