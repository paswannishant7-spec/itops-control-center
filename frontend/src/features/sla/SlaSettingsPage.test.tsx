import '@testing-library/jest-dom/vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AuthContext } from '../auth/authContextValue'
import { SlaSettingsPage } from './SlaSettingsPage'

const calendarId = '11111111-1111-4111-8111-111111111111'

function response(value: unknown) {
  return new Response(JSON.stringify(value), {
    headers: { 'Content-Type': 'application/json' },
  })
}

it('shows SLA configuration and saves a priority rule', async () => {
  const writes: Array<{ url: string; body: unknown }> = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input)
      if (init.method === 'PUT') {
        writes.push({ url, body: JSON.parse(String(init.body)) })
        return response({ impact: 'HIGH', urgency: 'HIGH', priority: 'HIGH' })
      }
      if (url.endsWith('/sla/priority-matrix'))
        return response([
          { impact: 'HIGH', urgency: 'HIGH', priority: 'CRITICAL' },
        ])
      if (url.endsWith('/sla/calendars'))
        return response([
          {
            id: calendarId,
            name: 'Default 24x7',
            timezone: 'UTC',
            is_active: true,
            is_default: true,
            windows: [{ weekday: 0, start_minute: 0, end_minute: 1440 }],
            holidays: [],
            created_at: '2026-09-09T10:00:00Z',
            updated_at: '2026-09-09T10:00:00Z',
          },
        ])
      if (url.endsWith('/sla/policies'))
        return response([
          {
            id: '22222222-2222-4222-8222-222222222222',
            name: 'P1 Critical',
            priority: 'CRITICAL',
            calendar_id: calendarId,
            response_target_minutes: 15,
            resolution_target_minutes: 120,
            at_risk_percent: 80,
            is_active: true,
            created_at: '2026-09-09T10:00:00Z',
            updated_at: '2026-09-09T10:00:00Z',
          },
        ])
      throw new Error(`Unhandled URL: ${url}`)
    }),
  )
  render(
    <AuthContext.Provider
      value={{
        user: {
          id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
          display_name: 'SLA Administrator',
          email: 'admin@example.com',
          status: 'ACTIVE',
          roles: ['ADMIN'],
          permissions: ['sla:view', 'sla:manage'],
        },
        accessToken: 'signed-token',
        loading: false,
        login: async () => {},
        logout: async () => {},
      }}
    >
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <SlaSettingsPage />
        </MemoryRouter>
      </QueryClientProvider>
    </AuthContext.Provider>,
  )
  expect(
    await screen.findByRole('heading', { name: 'Priority and SLA policy' }),
  ).toBeVisible()
  expect(await screen.findByText('P1 Critical')).toBeVisible()
  const priority = screen.getByLabelText('HIGH impact · HIGH urgency')
  await userEvent.selectOptions(priority, 'HIGH')
  expect(await screen.findByText('Priority rule saved.')).toBeVisible()
  expect(writes[0]).toEqual({
    url: expect.stringContaining('/sla/priority-matrix/HIGH/HIGH'),
    body: { priority: 'HIGH' },
  })
})
