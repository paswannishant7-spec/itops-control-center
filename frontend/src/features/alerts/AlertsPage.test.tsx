import '@testing-library/jest-dom/vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AuthContext } from '../auth/authContextValue'
import { AlertsPage } from './AlertsPage'

const alertId = '11111111-1111-4111-8111-111111111111'
const assetId = '22222222-2222-4222-8222-222222222222'
const agentId = '33333333-3333-4333-8333-333333333333'
const policyId = '44444444-4444-4444-8444-444444444444'
const ticketId = '55555555-5555-4555-8555-555555555555'
const notificationId = '66666666-6666-4666-8666-666666666666'
const teamId = '77777777-7777-4777-8777-777777777777'
const actorId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

function response(value: unknown) {
  return new Response(JSON.stringify(value), {
    headers: { 'Content-Type': 'application/json' },
  })
}

const alert = {
  id: alertId,
  policy_id: policyId,
  agent_id: agentId,
  asset_id: assetId,
  asset_tag: 'SRV-100',
  incident_ticket_id: ticketId,
  incident_reference: 'INC-20260913-ABC12345',
  source: 'DEVICE_AGENT',
  severity: 'CRITICAL',
  metric: 'CPU_PERCENT',
  threshold: 90,
  observed_value: 98,
  state: 'TRIGGERED',
  triggered_at: '2026-09-13T00:00:00Z',
  last_observed_at: '2026-09-13T00:01:00Z',
  acknowledged_at: null,
  resolved_at: null,
  suppressed_at: null,
}

it('shows alerts and performs lifecycle and policy actions', async () => {
  const requests: Array<[string, string]> = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input)
      requests.push([url, init.method ?? 'GET'])
      if (url.includes(`/alerts/${alertId}/acknowledge`))
        return response({
          ...alert,
          state: 'ACKNOWLEDGED',
          acknowledged_at: '2026-09-13T00:02:00Z',
        })
      if (url.endsWith('/alerts/policies') && init.method === 'POST')
        return response({
          id: '88888888-8888-4888-8888-888888888888',
          name: 'Memory warning',
          metric: 'MEMORY_PERCENT',
          operator: 'GREATER_THAN',
          threshold: 80,
          severity: 'WARNING',
          enabled: true,
          created_at: '2026-09-13T00:00:00Z',
          updated_at: '2026-09-13T00:00:00Z',
        })
      if (url.includes('/alerts/policies'))
        return response({
          items: [
            {
              id: policyId,
              name: 'Critical CPU',
              metric: 'CPU_PERCENT',
              operator: 'GREATER_THAN',
              threshold: 90,
              severity: 'CRITICAL',
              enabled: true,
              created_at: '2026-09-13T00:00:00Z',
              updated_at: '2026-09-13T00:00:00Z',
            },
          ],
          total: 1,
        })
      if (url.includes('/automation/rules'))
        return response({ items: [], total: 0 })
      if (url.includes('/directory/teams'))
        return response([
          {
            id: teamId,
            code: 'OPS',
            name: 'Operations',
            description: null,
            status: 'ACTIVE',
            department: null,
            location: null,
            member_count: 1,
            created_at: '2026-09-13T00:00:00Z',
            updated_at: '2026-09-13T00:00:00Z',
          },
        ])
      if (url.includes('/notifications/preferences/me'))
        return response({
          in_app_enabled: true,
          minimum_alert_severity: 'WARNING',
        })
      if (url.includes('/notifications?'))
        return response({
          items: [
            {
              id: notificationId,
              alert_id: alertId,
              ticket_id: ticketId,
              event_type: 'critical_alert',
              title: 'Critical device alert',
              body: 'CPU condition triggered.',
              read_at: null,
              created_at: '2026-09-13T00:01:00Z',
            },
          ],
          total: 1,
          unread: 1,
          offset: 0,
          limit: 50,
        })
      if (url.includes('/alerts?'))
        return response({ items: [alert], total: 1, offset: 0, limit: 100 })
      throw new Error(`Unhandled URL: ${url}`)
    }),
  )
  render(
    <AuthContext.Provider
      value={{
        user: {
          id: actorId,
          display_name: 'Alert Administrator',
          email: 'admin@example.com',
          status: 'ACTIVE',
          roles: ['ADMIN'],
          permissions: [
            'alert:view',
            'alert:acknowledge',
            'alert:resolve',
            'alert:manage',
          ],
        },
        accessToken: 'signed-token',
        loading: false,
        login: async () => {},
        logout: async () => {},
      }}
    >
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <AlertsPage />
        </MemoryRouter>
      </QueryClientProvider>
    </AuthContext.Provider>,
  )
  expect(await screen.findByText('SRV-100')).toBeVisible()
  expect(screen.getByText('INC-20260913-ABC12345')).toBeVisible()
  expect(await screen.findByText('Critical device alert')).toBeVisible()
  await userEvent.type(
    screen.getByLabelText('Reason for SRV-100'),
    'Investigating now',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Acknowledge' }))
  await vi.waitFor(() =>
    expect(requests.some(([url]) => url.includes('/acknowledge'))).toBe(true),
  )
  await userEvent.type(screen.getByLabelText('Policy name'), 'Memory warning')
  await userEvent.selectOptions(
    screen.getByLabelText('Metric'),
    'MEMORY_PERCENT',
  )
  await userEvent.type(screen.getByLabelText('Threshold'), '80')
  await userEvent.type(
    screen.getByLabelText('Policy reason'),
    'Add memory visibility',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Create policy' }))
  await vi.waitFor(() =>
    expect(
      requests.some(
        ([url, method]) =>
          url.endsWith('/alerts/policies') && method === 'POST',
      ),
    ).toBe(true),
  )
})
