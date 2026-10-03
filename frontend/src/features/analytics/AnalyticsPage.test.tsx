import '@testing-library/jest-dom/vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AuthContext } from '../auth/authContextValue'
import { AnalyticsPage } from './AnalyticsPage'

const ticketId = '11111111-1111-4111-8111-111111111111'
const userId = '22222222-2222-4222-8222-222222222222'
const agentId = '33333333-3333-4333-8333-333333333333'
const assetId = '44444444-4444-4444-8444-444444444444'
const alertId = '55555555-5555-4555-8555-555555555555'

function payload(audience: 'TEAM' | 'ORGANIZATION' = 'ORGANIZATION') {
  return {
    generated_at: '2026-09-13T12:00:00Z',
    scope: {
      audience,
      label:
        audience === 'TEAM'
          ? 'My teams and assignments'
          : 'Organization-wide operations',
      window_days: 30,
      window_start: '2026-08-14T12:00:00Z',
      window_end: '2026-09-13T12:00:00Z',
    },
    summary: {
      open_tickets: 18,
      assigned_to_me: 4,
      unassigned_tickets: 3,
      active_incidents: 5,
      critical_incidents: 2,
      sla_at_risk: 3,
      sla_breached: 1,
      online_devices: 21,
      offline_devices: 2,
      unhealthy_devices: 3,
      critical_alerts: 1,
    },
    performance: {
      mttr: { minutes: 84.5, sample_size: 12 },
      mtta: { minutes: 11.2, sample_size: 15 },
      sla_compliance: { percent: 91.7, sample_size: 12 },
      first_contact_resolution_proxy: { percent: 75, sample_size: 12 },
      reopen_rate: { percent: 8.3, sample_size: 12 },
    },
    ticket_volume: {
      daily: [
        { period_start: '2026-09-12', created: 4, resolved: 2 },
        { period_start: '2026-09-13', created: 2, resolved: 3 },
      ],
      weekly: [{ period_start: '2026-09-08', created: 6, resolved: 5 }],
      monthly: [{ period_start: '2026-09-01', created: 6, resolved: 5 }],
    },
    by_category: [{ label: 'Connectivity', count: 7 }],
    by_department: [{ label: 'Engineering', count: 6 }],
    by_priority: [{ label: 'HIGH', count: 8 }],
    technician_workload: [
      {
        technician_id: userId,
        technician_name: 'Taylor Technician',
        assigned_open: 5,
        resolved_in_window: 8,
      },
    ],
    recurring_issues: [
      { category: 'Connectivity', subcategory: 'VPN', ticket_count: 4 },
    ],
    asset_incident_frequency: [
      { asset_id: assetId, asset_tag: 'LT-200', incident_count: 3 },
    ],
    ai_assistance: {
      reviewed_recommendations: 12,
      accepted: 6,
      edited: 4,
      rejected: 2,
      regenerated: 1,
      acceptance_rate: 50,
      edit_rate: 33.3,
      rejection_rate: 16.7,
      label: 'Operational review rates; not a scientific AI accuracy measure.',
    },
    attention: {
      urgent_tickets: [
        {
          id: ticketId,
          reference: 'INC-1042',
          title: 'VPN gateway unavailable',
          priority: 'CRITICAL',
          status: 'ESCALATED',
          sla_state: 'BREACHED',
          updated_at: '2026-09-13T11:50:00Z',
        },
      ],
      device_health_issues: [
        {
          agent_id: agentId,
          asset_id: assetId,
          asset_tag: 'LT-200',
          hostname: 'field-laptop',
          status: 'OFFLINE',
          health_status: 'OFFLINE',
        },
      ],
      critical_alerts: [
        {
          id: alertId,
          asset_id: assetId,
          asset_tag: 'LT-200',
          severity: 'CRITICAL',
          metric: 'DEVICE_OFFLINE',
          state: 'TRIGGERED',
          triggered_at: '2026-09-13T11:45:00Z',
        },
      ],
    },
  }
}

function renderPage(audience: 'TEAM' | 'ORGANIZATION' = 'ORGANIZATION') {
  const fetch = vi.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify(payload(audience)), {
        headers: { 'Content-Type': 'application/json' },
      }),
  )
  vi.stubGlobal('fetch', fetch)
  render(
    <AuthContext.Provider
      value={{
        user: {
          id: userId,
          display_name: 'Morgan Manager',
          email: 'manager@example.com',
          status: 'ACTIVE',
          roles: ['IT_MANAGER'],
          permissions: ['analytics:view'],
        },
        accessToken: 'signed-token',
        loading: false,
        login: async () => {},
        logout: async () => {},
      }}
    >
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <AnalyticsPage />
        </MemoryRouter>
      </QueryClientProvider>
    </AuthContext.Provider>,
  )
  return fetch
}

it('renders the live organization command center from API metrics', async () => {
  renderPage()
  expect(
    await screen.findByRole('heading', { name: 'IT command center' }),
  ).toBeVisible()
  expect(await screen.findByText('Organization-wide operations')).toBeVisible()
  expect(screen.getByText('84.5m')).toBeVisible()
  expect(screen.getByText('91.7%')).toBeVisible()
  expect(
    screen.getByRole('img', { name: /daily created and resolved/i }),
  ).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'weekly' }))
  expect(
    screen.getByRole('img', { name: /weekly created and resolved/i }),
  ).toBeVisible()
  expect(screen.getByRole('link', { name: /INC-1042/ })).toHaveAttribute(
    'href',
    `/tickets/${ticketId}`,
  )
  expect(screen.getByText('Taylor Technician')).toBeVisible()
  expect(
    screen.getByRole('link', { name: /Linked incidents/ }),
  ).toHaveAttribute('href', `/assets/${assetId}`)
  expect(screen.getByText(/not a scientific AI accuracy measure/)).toBeVisible()
})

it('labels team scope as technician operations and reloads a selected window', async () => {
  const fetch = renderPage('TEAM')
  expect(
    await screen.findByRole('heading', { name: 'Technician operations' }),
  ).toBeVisible()
  expect(screen.getByText('My teams and assignments')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: '7d' }))
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
  expect(String(fetch.mock.calls[1]?.[0])).toContain('window_days=7')
})
