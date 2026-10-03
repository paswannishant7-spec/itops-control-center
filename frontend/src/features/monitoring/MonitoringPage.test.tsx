import '@testing-library/jest-dom/vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AuthContext } from '../auth/authContextValue'
import { MonitoringPage } from './MonitoringPage'

const agentId = '11111111-1111-4111-8111-111111111111'
const assetId = '22222222-2222-4222-8222-222222222222'

function response(value: unknown) {
  return new Response(JSON.stringify(value), {
    headers: { 'Content-Type': 'application/json' },
  })
}

it('shows scoped telemetry and creates a one-time enrollment token', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input)
      if (url.includes('/monitoring/enrollments') && init.method === 'POST')
        return response({
          agent_id: agentId,
          device_id: assetId,
          enrollment_token: 'one-time-enrollment-token-value',
          expires_at: '2026-09-13T01:00:00Z',
        })
      if (url.includes(`/monitoring/agents/${agentId}/metrics`))
        return response({
          items: [
            {
              id: '33333333-3333-4333-8333-333333333333',
              sampled_at: '2026-09-13T00:00:00Z',
              received_at: '2026-09-13T00:00:01Z',
              cpu_percent: 15,
              memory_percent: 40,
              memory_used_bytes: 4000,
              memory_total_bytes: 10000,
              disk_percent: 50,
              disk_used_bytes: 5000,
              disk_total_bytes: 10000,
              network_bytes_sent: 2048,
              network_bytes_received: 4096,
            },
          ],
          total: 1,
          offset: 0,
          limit: 100,
        })
      if (url.includes('/monitoring/agents'))
        return response({
          items: [
            {
              agent_id: agentId,
              device_id: assetId,
              asset_tag: 'LT-300',
              hostname: 'support-laptop',
              status: 'ONLINE',
              credential_status: 'ACTIVE',
              credential_prefix: 'prefix12',
              last_seen: '2026-09-13T00:00:01Z',
              last_heartbeat: '2026-09-13T00:00:01Z',
              missed_heartbeat_count: 0,
              agent_version: '0.1.0',
              enrolled_at: '2026-09-12T23:00:00Z',
            },
          ],
          total: 1,
          offset: 0,
          limit: 100,
        })
      if (url.includes('/assets?'))
        return response({
          items: [
            {
              id: assetId,
              asset_tag: 'LT-300',
              serial_number: null,
              hostname: 'support-laptop',
              asset_type: 'LAPTOP',
              manufacturer: null,
              model: null,
              operating_system: null,
              ip_address: null,
              mac_address: null,
              owner: null,
              department: null,
              location: null,
              purchase_date: null,
              warranty_end: null,
              status: 'ACTIVE',
              last_seen: null,
              health_status: 'UNKNOWN',
              created_at: '2026-09-12T20:00:00Z',
              updated_at: '2026-09-12T20:00:00Z',
            },
          ],
          total: 1,
          offset: 0,
          limit: 100,
        })
      throw new Error(`Unhandled URL: ${url}`)
    }),
  )
  render(
    <AuthContext.Provider
      value={{
        user: {
          id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
          display_name: 'Monitoring Administrator',
          email: 'admin@example.com',
          status: 'ACTIVE',
          roles: ['ADMIN'],
          permissions: ['monitoring:view', 'monitoring:manage'],
        },
        accessToken: 'signed-token',
        loading: false,
        login: async () => {},
        logout: async () => {},
      }}
    >
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <MonitoringPage />
        </MemoryRouter>
      </QueryClientProvider>
    </AuthContext.Provider>,
  )
  expect(await screen.findByText('LT-300')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: /LT-300/ }))
  expect(await screen.findByText('15.0%')).toBeVisible()
  await userEvent.selectOptions(screen.getByLabelText('Asset'), assetId)
  await userEvent.type(
    screen.getByLabelText('Reason'),
    'Enroll supported endpoint',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Create token' }))
  expect(
    await screen.findByText('one-time-enrollment-token-value'),
  ).toBeVisible()
  expect(screen.getByText(/shown only once/i)).toBeVisible()
})
