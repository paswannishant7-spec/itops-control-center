import '@testing-library/jest-dom/vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AuthContext } from '../auth/authContextValue'
import { DirectoryPage } from './DirectoryPage'

const department = {
  id: '11111111-1111-4111-8111-111111111111',
  code: 'IT',
  name: 'Information Technology',
  description: 'Internal technology',
  status: 'ACTIVE',
  user_count: 1,
  team_count: 1,
  created_at: '2026-09-09T00:00:00Z',
  updated_at: '2026-09-09T00:00:00Z',
}
const location = {
  id: '22222222-2222-4222-8222-222222222222',
  code: 'HQ',
  name: 'Headquarters',
  timezone: 'UTC',
  address: 'Technology campus',
  status: 'ACTIVE',
  user_count: 1,
  team_count: 1,
  created_at: '2026-09-09T00:00:00Z',
  updated_at: '2026-09-09T00:00:00Z',
}
const team = {
  id: '33333333-3333-4333-8333-333333333333',
  code: 'SERVICE_DESK',
  name: 'Service Desk',
  description: 'Regional support',
  status: 'ACTIVE',
  department,
  location,
  member_count: 0,
  created_at: '2026-09-09T00:00:00Z',
  updated_at: '2026-09-09T00:00:00Z',
}
const candidate = {
  id: '44444444-4444-4444-8444-444444444444',
  display_name: 'Casey Technician',
  email: 'casey@example.com',
  job_title: 'Technician',
  roles: ['TECHNICIAN'],
}

function response(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function setup(permissions: string[]) {
  render(
    <AuthContext.Provider
      value={{
        user: {
          id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
          email: 'operator@example.com',
          display_name: 'Operator',
          status: 'ACTIVE',
          roles: ['ADMIN'],
          permissions,
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
          <DirectoryPage />
        </MemoryRouter>
      </QueryClientProvider>
    </AuthContext.Provider>,
  )
}

it('shows the authorized user, team, department, and location work areas', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/directory/users?'))
        return response({ items: [], total: 0, offset: 0, limit: 10 })
      if (url.endsWith('/directory/teams')) return response([])
      if (url.endsWith('/directory/departments')) return response([department])
      if (url.endsWith('/directory/locations')) return response([location])
      throw new Error(`Unhandled test URL: ${url}`)
    }),
  )
  setup([
    'team:view',
    'team:manage',
    'user:view',
    'user:create',
    'user:update',
    'user:disable',
    'role:manage',
    'department:view',
    'department:manage',
    'location:view',
    'location:manage',
  ])
  expect(await screen.findByRole('heading', { name: 'Users' })).toBeVisible()
  expect(screen.getByRole('heading', { name: 'Teams' })).toBeVisible()
  expect(screen.getByRole('heading', { name: 'Departments' })).toBeVisible()
  expect(screen.getByRole('heading', { name: 'Locations' })).toBeVisible()
  expect(
    await screen.findByRole('cell', { name: 'Information Technology' }),
  ).toBeVisible()
  expect(
    await screen.findByRole('cell', { name: 'Headquarters' }),
  ).toBeVisible()
  expect(screen.getByText('Create user account')).toBeVisible()
})

it('lets an IT manager assign an eligible technician without broad user access', async () => {
  const writes: RequestInit[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input)
      if (init.method === 'PUT' && url.includes('/members/')) {
        writes.push(init)
        return response({
          user_id: candidate.id,
          display_name: candidate.display_name,
          email: candidate.email,
          job_title: candidate.job_title,
          status: 'ACTIVE',
          member_role: 'LEAD',
          roles: candidate.roles,
        })
      }
      if (url.includes('/eligible-technicians')) return response([candidate])
      if (url.endsWith(`/directory/teams/${team.id}`))
        return response({ ...team, members: [] })
      if (url.endsWith('/directory/teams')) return response([team])
      if (url.endsWith('/directory/departments')) return response([department])
      if (url.endsWith('/directory/locations')) return response([location])
      throw new Error(`Unhandled test URL: ${url}`)
    }),
  )
  setup(['team:view', 'team:manage', 'department:view', 'location:view'])
  const visitor = userEvent.setup()
  await visitor.click(
    await screen.findByRole('button', { name: /Service Desk/ }),
  )
  const assignment = await screen.findByRole('heading', {
    name: 'Assign technician',
  })
  const form = assignment.closest('form')!
  await visitor.selectOptions(
    within(form).getByLabelText('Technician'),
    candidate.id,
  )
  await visitor.selectOptions(
    within(form).getByLabelText('Team-level role'),
    'LEAD',
  )
  await visitor.type(
    within(form).getByLabelText('Reason for membership change'),
    'Primary escalation owner',
  )
  await visitor.click(
    within(form).getByRole('button', { name: 'Assign technician' }),
  )
  expect(await screen.findByText(/was assigned to the team/)).toBeVisible()
  expect(JSON.parse(String(writes[0].body))).toEqual({
    member_role: 'LEAD',
    reason: 'Primary escalation owner',
  })
  expect(
    screen.queryByRole('heading', { name: 'Users' }),
  ).not.toBeInTheDocument()
})

it('surfaces a backend denial with its correlation identifier', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/directory/teams'))
        return response(
          {
            title: 'Permission denied',
            code: 'http_error',
            request_id: 'request-123',
          },
          403,
        )
      if (url.endsWith('/directory/departments')) return response([])
      if (url.endsWith('/directory/locations')) return response([])
      throw new Error(`Unhandled test URL: ${url}`)
    }),
  )
  setup(['team:view', 'department:view', 'location:view'])
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Permission denied (request request-123)',
  )
})
