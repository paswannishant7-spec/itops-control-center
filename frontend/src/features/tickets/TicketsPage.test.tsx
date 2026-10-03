import '@testing-library/jest-dom/vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthContext } from '../auth/authContextValue'
import { TicketDetailPage } from './TicketDetailPage'
import { TicketsPage } from './TicketsPage'

const userId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const ticketId = '11111111-1111-4111-8111-111111111111'
const person = {
  id: userId,
  display_name: 'Morgan Employee',
  email: 'morgan@example.com',
}
const summary = {
  id: ticketId,
  reference: 'IT-20260909-ABC12345',
  title: 'VPN connection fails after sign in',
  requester: person,
  department: {
    id: '22222222-2222-4222-8222-222222222222',
    name: 'Information Technology',
  },
  location: null,
  impact: 'MEDIUM',
  urgency: 'HIGH',
  priority: 'HIGH',
  sla_state: 'AT_RISK',
  status: 'RESOLVED',
  assignment_team: null,
  assigned_technician: null,
  source: 'PORTAL',
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T11:00:00Z',
}
const detail = {
  ...summary,
  description: 'The VPN gateway cannot be reached after authentication.',
  asset_id: null,
  category: null,
  subcategory: null,
  first_response_at: '2026-09-09T10:15:00Z',
  resolved_at: '2026-09-09T11:00:00Z',
  closed_at: null,
  reopened_at: null,
  resolution_summary: 'Reissued the VPN profile.',
  resolution_code: 'CONFIGURATION_REPAIRED',
}

function response(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function setup(
  component: React.ReactNode,
  permissions: string[],
  initial = '/tickets',
) {
  render(
    <AuthContext.Provider
      value={{
        user: {
          ...person,
          status: 'ACTIVE',
          roles: ['EMPLOYEE'],
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
        <MemoryRouter initialEntries={[initial]}>{component}</MemoryRouter>
      </QueryClientProvider>
    </AuthContext.Provider>,
  )
}

it('lists visible tickets and creates a support request', async () => {
  const writes: RequestInit[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input)
      if (init.method === 'POST' && url.endsWith('/tickets')) {
        writes.push(init)
        return response({ ...detail, status: 'NEW', resolution_summary: null })
      }
      if (url.includes('/tickets?'))
        return response({ items: [summary], total: 1, offset: 0, limit: 25 })
      throw new Error(`Unhandled test URL: ${url}`)
    }),
  )
  setup(
    <Routes>
      <Route path="/tickets" element={<TicketsPage />} />
      <Route path="/tickets/:ticketId" element={<h1>Created ticket</h1>} />
    </Routes>,
    ['ticket:create', 'ticket:view_own'],
  )
  expect(await screen.findByText(summary.reference)).toBeVisible()
  expect(screen.getByText(summary.title)).toBeVisible()
  const ticketCells = within(
    screen.getByText(summary.reference).closest('tr')!,
  ).getAllByRole('cell')
  expect(ticketCells[1]).toHaveTextContent('RESOLVED')
  expect(ticketCells[2]).toHaveTextContent('HIGH')
  expect(ticketCells[3]).toHaveTextContent('AT RISK')
  const visitor = userEvent.setup()
  await visitor.click(screen.getByRole('button', { name: 'Create ticket' }))
  const form = screen
    .getByRole('heading', { name: 'New support request' })
    .closest('section')!
  await visitor.type(
    within(form).getByLabelText('Title'),
    'Email client will not start',
  )
  await visitor.type(
    within(form).getByLabelText('Description'),
    'The desktop client closes immediately after launch.',
  )
  await visitor.selectOptions(within(form).getByLabelText('Impact'), 'LOW')
  await visitor.selectOptions(within(form).getByLabelText('Urgency'), 'MEDIUM')
  await visitor.click(
    within(form).getByRole('button', { name: 'Submit request' }),
  )
  expect(
    await screen.findByRole('heading', { name: 'Created ticket' }),
  ).toBeVisible()
  expect(JSON.parse(String(writes[0].body))).toEqual({
    title: 'Email client will not start',
    description: 'The desktop client closes immediately after launch.',
    impact: 'LOW',
    urgency: 'MEDIUM',
  })
})

it('renders the support workstation and lets the requester reopen and comment', async () => {
  const writes: Array<{ url: string; body: unknown }> = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input)
      if (init.method === 'POST' && url.endsWith('/comments')) {
        writes.push({ url, body: JSON.parse(String(init.body)) })
        return response({
          id: '33333333-3333-4333-8333-333333333333',
          author: person,
          body: 'The problem has returned.',
          visibility: 'PUBLIC',
          created_at: '2026-09-09T12:00:00Z',
          updated_at: '2026-09-09T12:00:00Z',
        })
      }
      if (init.method === 'POST' && url.endsWith('/transitions')) {
        writes.push({ url, body: JSON.parse(String(init.body)) })
        return response({
          ...detail,
          status: 'OPEN',
          resolution_summary: null,
          resolution_code: null,
          resolved_at: null,
          reopened_at: '2026-09-09T12:01:00Z',
        })
      }
      if (url.endsWith(`/sla/tickets/${ticketId}`))
        return response({
          instance_id: '55555555-5555-4555-8555-555555555555',
          policy_name: 'P2 High',
          calendar_name: 'Default 24x7',
          calendar_timezone: 'UTC',
          state: 'AT_RISK',
          active_target: 'RESOLUTION',
          response_target_seconds: 3600,
          resolution_target_seconds: 28800,
          response_elapsed_seconds: 900,
          resolution_elapsed_seconds: 23040,
          elapsed_seconds: 23040,
          remaining_seconds: 5760,
          percentage: 80,
          is_paused: false,
          response_breached_at: null,
          resolution_breached_at: null,
          escalated_at: null,
          last_evaluated_at: '2026-09-09T10:30:00Z',
        })
      if (url.endsWith(`/tickets/${ticketId}`)) return response(detail)
      if (url.includes('/comments?'))
        return response({ items: [], total: 0, offset: 0, limit: 100 })
      if (url.endsWith('/attachments')) return response([])
      if (url.includes('/events?'))
        return response({
          items: [
            {
              id: '44444444-4444-4444-8444-444444444444',
              event_type: 'ticket.created',
              actor: person,
              before_state: null,
              after_state: { status: 'NEW' },
              reason: 'Ticket submitted',
              created_at: '2026-09-09T10:00:00Z',
            },
          ],
          total: 1,
          offset: 0,
          limit: 100,
        })
      throw new Error(`Unhandled test URL: ${url}`)
    }),
  )
  setup(
    <Routes>
      <Route path="/tickets/:ticketId" element={<TicketDetailPage />} />
    </Routes>,
    ['ticket:view_own', 'ticket:comment', 'ticket:reopen'],
    `/tickets/${ticketId}`,
  )
  expect(
    await screen.findByRole('heading', { name: detail.title }),
  ).toBeVisible()
  expect(screen.getByText('Reissued the VPN profile.')).toBeVisible()
  expect(await screen.findByText('P2 High')).toBeVisible()
  expect(screen.getByText(/80.0% used/)).toBeVisible()
  expect(await screen.findByText('ticket created')).toBeVisible()
  const visitor = userEvent.setup()
  await visitor.type(
    screen.getByLabelText('Reply'),
    'The problem has returned.',
  )
  await visitor.click(screen.getByRole('button', { name: 'Add message' }))
  expect(await screen.findByText('Comment added.')).toBeVisible()
  await visitor.type(
    screen.getByLabelText('Reason'),
    'Connectivity failed again',
  )
  await visitor.click(screen.getByRole('button', { name: 'Apply transition' }))
  expect(await screen.findByText('Status updated.')).toBeVisible()
  expect(writes.map((value) => value.body)).toContainEqual({
    body: 'The problem has returned.',
  })
  expect(writes.map((value) => value.body)).toContainEqual({
    status: 'OPEN',
    reason: 'Connectivity failed again',
  })
})

it('shows correlated ticket API failures with a retry action', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      response(
        {
          title: 'Ticket query failed',
          code: 'http_error',
          request_id: 'ticket-request-42',
        },
        503,
      ),
    ),
  )
  setup(<TicketsPage />, ['ticket:create', 'ticket:view_own'])
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Ticket query failed (request ticket-request-42)',
  )
  expect(screen.getByRole('button', { name: 'Retry' })).toBeVisible()
})

it('generates and presents advisory AI classification in the ticket workflow', async () => {
  const classification = {
    interaction_id: '66666666-6666-4666-8666-666666666666',
    ticket_id: ticketId,
    source: 'MODEL',
    provider: 'test-provider',
    model: 'test-classifier-v1',
    status: 'SUCCEEDED',
    confidence_band: 'HIGH',
    fallback_reason: null,
    recommendation: {
      category_id: '77777777-7777-4777-8777-777777777777',
      subcategory_id: '88888888-8888-4888-8888-888888888888',
      category: 'Network access',
      subcategory: 'VPN',
      impact: 'MEDIUM',
      urgency: 'HIGH',
      priority_recommendation: 'HIGH',
      possible_causes: ['Expired managed VPN profile'],
      recommended_checks: ['Verify the profile issue date'],
      confidence: 0.93,
    },
    created_at: '2026-09-09T12:00:00Z',
  }
  const troubleshooting = {
    interaction_id: '99999999-9999-4999-8999-999999999999',
    ticket_id: ticketId,
    source: 'MODEL',
    provider: 'test-provider',
    model: 'test-troubleshooter-v1',
    status: 'SUCCEEDED',
    confidence_band: 'MODERATE',
    fallback_reason: null,
    recommendation: {
      summary: 'The published VPN procedure matches this symptom.',
      known_facts: ['Authentication completes before the failure.'],
      possible_causes: ['A stale managed VPN profile'],
      recommended_actions: ['Reissue the managed VPN profile.'],
      uncertain_assumptions: ['The endpoint is enrolled.'],
      cited_chunk_ids: ['aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'],
      confidence: 0.84,
    },
    citations: [
      {
        article_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        version_id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
        chunk_id: 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
        article_slug: 'repair-vpn-profile',
        article_title: 'Repair a managed VPN profile',
        article_version: 3,
        chunk_ordinal: 0,
        excerpt: 'Replace the managed VPN profile and verify connectivity.',
        similarity: 0.91,
      },
    ],
    created_at: '2026-09-09T12:01:00Z',
  }
  const similarTickets = {
    ticket_id: ticketId,
    provider: 'test-provider',
    model: 'test-embedding-v1',
    indexed_embeddings: 2,
    reused_embeddings: 4,
    items: [
      {
        ticket_id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
        reference: 'IT-20260901-SIMILAR',
        title: 'Managed VPN profile fails after login',
        similarity: 0.92,
        status: 'RESOLVED',
        priority: 'HIGH',
        category: 'Network access',
        subcategory: 'VPN',
        resolution_summary: 'Reissued the managed VPN profile.',
        resolution_code: 'CONFIGURATION_REPAIRED',
        resolved_at: '2026-09-01T14:00:00Z',
        closed_at: null,
      },
    ],
  }
  const responseDraft = {
    interaction_id: '10101010-1010-4010-8010-101010101010',
    recommendation_id: '11111111-aaaa-4111-8111-111111111111',
    ticket_id: ticketId,
    task_type: 'RESPONSE_DRAFT',
    source: 'MODEL',
    provider: 'test-provider',
    model: 'test-assistant-v1',
    status: 'SUCCEEDED',
    confidence_band: 'MODERATE',
    fallback_reason: null,
    recommendation: {
      draft:
        'Please restart the VPN client and let us know whether connectivity returns.',
      key_points: ['Request confirmation after the safe check'],
      safety_notes: ['Never request credentials'],
      confidence: 0.81,
    },
    feedback: null,
    created_at: '2026-09-11T10:00:00Z',
  }
  const ticketSummary = {
    interaction_id: '12121212-1212-4212-8212-121212121212',
    recommendation_id: '13131313-1313-4313-8313-131313131313',
    ticket_id: ticketId,
    task_type: 'SUMMARIZATION',
    source: 'MODEL',
    provider: 'test-provider',
    model: 'test-assistant-v1',
    status: 'SUCCEEDED',
    confidence_band: 'MODERATE',
    fallback_reason: null,
    recommendation: {
      summary: 'The managed VPN connection fails after authentication.',
      key_facts: ['Authentication completes'],
      open_questions: ['Is the managed profile current?'],
      suggested_next_step: 'Verify the profile issue date.',
      confidence: 0.78,
    },
    feedback: null,
    created_at: '2026-09-11T10:01:00Z',
  }
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input)
      if (init.method === 'POST' && url.endsWith('/classifications'))
        return response(classification, 201)
      if (init.method === 'POST' && url.endsWith('/troubleshooting'))
        return response(troubleshooting, 201)
      if (init.method === 'POST' && url.endsWith('/similar'))
        return response(similarTickets)
      if (init.method === 'POST' && url.endsWith('/assistant/RESPONSE_DRAFT'))
        return response(responseDraft, 201)
      if (init.method === 'POST' && url.endsWith('/assistant/SUMMARIZATION'))
        return response(ticketSummary, 201)
      if (init.method === 'POST' && url.endsWith('/feedback')) {
        const body = JSON.parse(String(init.body)) as {
          action: 'ACCEPTED' | 'EDITED' | 'REJECTED' | 'REGENERATED'
          edited_content?: string
        }
        return response(
          {
            id: '14141414-1414-4414-8414-141414141414',
            interaction_id: responseDraft.interaction_id,
            recommendation_id: responseDraft.recommendation_id,
            ticket_id: ticketId,
            actor_id: '22222222-2222-4222-8222-222222222222',
            action: body.action,
            feedback_text: null,
            edited_content: body.edited_content ?? null,
            confidence: 0.81,
            output_type: 'RESPONSE_DRAFT',
            created_at: '2026-09-11T10:02:00Z',
          },
          201,
        )
      }
      if (url.endsWith('/classifications/latest')) return response(null)
      if (url.endsWith('/troubleshooting/latest')) return response(null)
      if (url.includes('/assistant/') && url.endsWith('/latest'))
        return response(null)
      if (url.endsWith(`/sla/tickets/${ticketId}`)) return response(null)
      if (url.endsWith(`/tickets/${ticketId}`)) return response(detail)
      if (url.includes('/comments?'))
        return response({ items: [], total: 0, offset: 0, limit: 100 })
      if (url.endsWith('/attachments')) return response([])
      if (url.includes('/events?'))
        return response({ items: [], total: 0, offset: 0, limit: 100 })
      throw new Error(`Unhandled test URL: ${url}`)
    }),
  )
  setup(
    <Routes>
      <Route path="/tickets/:ticketId" element={<TicketDetailPage />} />
    </Routes>,
    ['ticket:view_all', 'ticket:comment', 'ai:use'],
    `/tickets/${ticketId}`,
  )
  expect(
    await screen.findByText('No classification has been generated.'),
  ).toBeVisible()
  await userEvent.click(
    screen.getByRole('button', { name: 'Generate classification' }),
  )
  expect(await screen.findByText('Network access')).toBeVisible()
  expect(screen.getByText('Expired managed VPN profile')).toBeVisible()
  expect(screen.getByText('HIGH · 93%')).toBeVisible()
  expect(screen.getByText(/Advisory only/)).toBeVisible()
  expect(
    screen.getByText('No grounded guidance has been generated.'),
  ).toBeVisible()
  await userEvent.click(
    screen.getByRole('button', { name: 'Generate grounded guidance' }),
  )
  expect(
    await screen.findByText(troubleshooting.recommendation.summary),
  ).toBeVisible()
  expect(screen.getByText('Reissue the managed VPN profile.')).toBeVisible()
  expect(
    screen.getByRole('link', { name: /Repair a managed VPN profile/ }),
  ).toHaveAttribute(
    'href',
    `/knowledge/${troubleshooting.citations[0].article_id}`,
  )
  expect(await screen.findByText('92% similar')).toBeVisible()
  expect(
    screen.getByText(similarTickets.items[0].resolution_summary),
  ).toBeVisible()
  expect(
    screen.getByRole('link', { name: /IT-20260901-SIMILAR/ }),
  ).toHaveAttribute('href', `/tickets/${similarTickets.items[0].ticket_id}`)
  expect(screen.getByText(/not an exact diagnosis/)).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Draft response' }))
  expect(
    await screen.findByDisplayValue(responseDraft.recommendation.draft),
  ).toBeVisible()
  expect(screen.getByText('Never request credentials')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Approve draft' }))
  expect(await screen.findByText('Review recorded: ACCEPTED')).toBeVisible()
  expect(screen.getByRole('textbox', { name: 'Reply' })).toHaveValue(
    responseDraft.recommendation.draft,
  )
  expect(screen.getByText(/never posts or changes the ticket/)).toBeVisible()

  await userEvent.click(
    screen.getByRole('button', { name: 'Summarize ticket' }),
  )
  expect(
    await screen.findByText(ticketSummary.recommendation.summary),
  ).toBeVisible()
  expect(
    screen.getByText(ticketSummary.recommendation.suggested_next_step),
  ).toBeVisible()
})
