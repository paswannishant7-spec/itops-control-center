import { mkdirSync } from 'node:fs'
import path from 'node:path'
import { expect, test, type Page, type Route } from '@playwright/test'

const userId = '73bb9477-5b69-4ee5-aacf-e80ed38a2520'
const ticketId = '63bb9477-5b69-4ee5-aacf-e80ed38a2520'
const assetId = '43bb9477-5b69-4ee5-aacf-e80ed38a2520'
const screenshotDirectory = path.resolve(
  process.cwd(),
  'test-results',
  'fixture-screenshots',
)

const grants = [
  'ticket:create',
  'ticket:view_all',
  'asset:view_all',
  'monitoring:view',
  'alert:view',
  'analytics:view',
  'audit:view',
]

const headers = {
  'access-control-allow-origin': 'http://127.0.0.1:4173',
  'access-control-allow-credentials': 'true',
  'content-type': 'application/json',
}

const tickets = [
  [
    'INC-1042',
    'Regional VPN access unavailable',
    'CRITICAL',
    'OPEN',
    'AT_RISK',
  ],
  [
    'INC-1038',
    'Finance printer queue stalled',
    'HIGH',
    'IN_PROGRESS',
    'ON_TRACK',
  ],
  [
    'REQ-1033',
    'New starter access package',
    'MEDIUM',
    'PENDING_USER',
    'PAUSED',
  ],
  ['INC-1029', 'Meeting room display offline', 'LOW', 'OPEN', 'ON_TRACK'],
] as const

function tokenResponse() {
  return {
    access_token: 'portfolio-demo-access-token',
    token_type: 'bearer',
    expires_in: 3600,
    user: {
      id: userId,
      email: 'maya.chen@example.test',
      display_name: 'Maya Chen',
      status: 'ACTIVE',
      roles: ['ADMIN'],
      permissions: grants,
    },
  }
}

async function json(route: Route, body: object) {
  await route.fulfill({ status: 200, headers, body: JSON.stringify(body) })
}

function ticketItems() {
  return tickets.map(
    ([reference, title, priority, status, slaState], index) => ({
      id:
        index === 0 ? ticketId : `${index}3bb9477-5b69-4ee5-aacf-e80ed38a2520`,
      reference,
      title,
      requester: {
        id: userId,
        display_name: index === 2 ? 'Ari Patel' : 'Jordan Lee',
        email: index === 2 ? 'ari@example.test' : 'jordan@example.test',
      },
      department: {
        id: '33bb9477-5b69-4ee5-aacf-e80ed38a2520',
        name: index === 1 ? 'Finance' : 'Operations',
      },
      location: null,
      impact: index < 2 ? 'HIGH' : 'MEDIUM',
      urgency: index === 0 ? 'HIGH' : 'MEDIUM',
      priority,
      sla_state: slaState,
      status,
      assignment_team: {
        id: '23bb9477-5b69-4ee5-aacf-e80ed38a2520',
        name: 'Service Desk',
      },
      assigned_technician:
        index === 0
          ? null
          : {
              id: userId,
              display_name: 'Maya Chen',
              email: 'maya.chen@example.test',
            },
      record_type: reference.startsWith('INC') ? 'INCIDENT' : 'REQUEST',
      source: 'PORTAL',
      created_at: `2026-09-${16 - index}T08:00:00Z`,
      updated_at: `2026-09-17T0${8 - index}:15:00Z`,
    }),
  )
}

function dashboard() {
  const daily = [
    [10, 8],
    [14, 11],
    [9, 13],
    [18, 14],
    [22, 17],
    [16, 19],
    [12, 15],
  ].map(([created, resolved], index) => ({
    period_start: `2026-09-${11 + index}T00:00:00Z`,
    created,
    resolved,
  }))
  return {
    generated_at: '2026-09-17T08:30:00Z',
    scope: {
      audience: 'ORGANIZATION',
      label: 'Organization-wide operations',
      window_days: 30,
      window_start: '2026-08-19T00:00:00Z',
      window_end: '2026-09-17T23:59:59Z',
    },
    summary: {
      open_tickets: 34,
      assigned_to_me: 7,
      unassigned_tickets: 4,
      active_incidents: 12,
      critical_incidents: 1,
      sla_at_risk: 5,
      sla_breached: 2,
      online_devices: 286,
      offline_devices: 9,
      unhealthy_devices: 6,
      critical_alerts: 3,
    },
    performance: {
      mttr: { minutes: 184, sample_size: 87 },
      mtta: { minutes: 12, sample_size: 96 },
      sla_compliance: { percent: 94.2, sample_size: 87 },
      first_contact_resolution_proxy: { percent: 68.4, sample_size: 87 },
      reopen_rate: { percent: 4.6, sample_size: 87 },
    },
    ticket_volume: {
      daily,
      weekly: daily.slice(0, 4),
      monthly: daily.slice(0, 3),
    },
    by_category: [
      { label: 'Access & identity', count: 31 },
      { label: 'Connectivity', count: 24 },
      { label: 'Hardware', count: 18 },
    ],
    by_department: [
      { label: 'Operations', count: 27 },
      { label: 'Finance', count: 19 },
      { label: 'Sales', count: 16 },
    ],
    by_priority: [
      { label: 'Critical', count: 3 },
      { label: 'High', count: 17 },
      { label: 'Medium', count: 49 },
      { label: 'Low', count: 22 },
    ],
    technician_workload: [
      {
        technician_id: userId,
        technician_name: 'Maya Chen',
        assigned_open: 7,
        resolved_in_window: 23,
      },
      {
        technician_id: '13bb9477-5b69-4ee5-aacf-e80ed38a2520',
        technician_name: 'Noah Williams',
        assigned_open: 9,
        resolved_in_window: 18,
      },
    ],
    recurring_issues: [
      { category: 'Connectivity', subcategory: 'VPN', ticket_count: 11 },
      { category: 'Access & identity', subcategory: 'MFA', ticket_count: 8 },
    ],
    asset_incident_frequency: [
      { asset_id: assetId, asset_tag: 'NET-LON-004', incident_count: 6 },
    ],
    ai_assistance: {
      reviewed_recommendations: 64,
      accepted: 45,
      edited: 12,
      rejected: 7,
      regenerated: 4,
      acceptance_rate: 70.3,
      edit_rate: 18.8,
      rejection_rate: 10.9,
      label: 'Technician-reviewed outcomes only',
    },
    attention: {
      urgent_tickets: ticketItems()
        .slice(0, 2)
        .map((ticket) => ({
          id: ticket.id,
          reference: ticket.reference,
          title: ticket.title,
          priority: ticket.priority,
          status: ticket.status,
          sla_state: ticket.sla_state,
          updated_at: ticket.updated_at,
        })),
      device_health_issues: [
        {
          agent_id: '03bb9477-5b69-4ee5-aacf-e80ed38a2520',
          asset_id: assetId,
          asset_tag: 'NET-LON-004',
          hostname: 'edge-lon-04',
          status: 'OFFLINE',
          health_status: 'CRITICAL',
        },
      ],
      critical_alerts: [
        {
          id: '93bb9477-5b69-4ee5-aacf-e80ed38a2520',
          asset_id: assetId,
          asset_tag: 'NET-LON-004',
          severity: 'CRITICAL',
          metric: 'heartbeat_age',
          state: 'OPEN',
          triggered_at: '2026-09-17T08:12:00Z',
        },
      ],
    },
  }
}

function auditEvents() {
  const values = [
    ['TICKET', 'ticket.priority.changed', 'Impact confirmed by incident lead'],
    ['ACCESS', 'role.assignment.updated', 'Quarterly access review'],
    ['ASSET', 'asset.owner.changed', 'Device issued to new starter'],
    ['AI', 'recommendation.accepted', 'Technician approved grounded response'],
  ] as const
  return values.map(([source, action, reason], index) => ({
    id: `${9 - index}3bb9477-5b69-4ee5-aacf-e80ed38a2520`,
    source,
    action,
    entity_type: source,
    entity_id:
      index === 0
        ? ticketId
        : `${8 - index}3bb9477-5b69-4ee5-aacf-e80ed38a2520`,
    actor_id: userId,
    before_state: { status: 'OPEN' },
    after_state: { status: 'REVIEWED' },
    reason,
    request_id: `portfolio-request-${index + 1}`,
    created_at: `2026-09-17T0${8 - index}:20:00Z`,
  }))
}

async function mockPortfolioApi(page: Page) {
  await page.routeWebSocket(
    'ws://localhost:8000/api/v1/realtime/ws',
    (socket) => {
      socket.onMessage(() =>
        socket.send(
          JSON.stringify({
            type: 'ready',
            protocol: 1,
            cursor: 0,
            topics: ['tickets', 'sla', 'alerts', 'notifications', 'devices'],
            heartbeat_seconds: 30,
          }),
        ),
      )
    },
  )
  await page.route('http://localhost:8000/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/auth/refresh'))
      return json(route, tokenResponse())
    if (url.pathname.endsWith('/access/me'))
      return json(route, { roles: ['ADMIN'], permissions: grants })
    if (url.pathname.endsWith('/analytics/dashboard'))
      return json(route, dashboard())
    if (url.pathname.endsWith('/tickets'))
      return json(route, {
        items: ticketItems(),
        total: ticketItems().length,
        offset: 0,
        limit: 25,
      })
    if (url.pathname.endsWith('/audit/events'))
      return json(route, {
        items: auditEvents(),
        total: auditEvents().length,
        offset: 0,
        limit: 50,
      })
    await route.fulfill({
      status: 404,
      headers,
      body: JSON.stringify({ title: `Unmocked request: ${url.pathname}` }),
    })
  })
}

async function prepare(page: Page) {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await mockPortfolioApi(page)
  await page.addStyleTag({
    content: '* { caret-color: transparent !important; }',
  })
}

async function capture(page: Page, name: string) {
  mkdirSync(screenshotDirectory, { recursive: true })
  await page.screenshot({
    path: path.join(screenshotDirectory, name),
    animations: 'disabled',
  })
}

test.describe('portfolio screenshots', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(
      process.env.CAPTURE_PORTFOLIO !== '1' ||
        testInfo.project.name !== 'chromium',
      'Run explicitly to capture test-only fixture screenshots.',
    )
    await prepare(page)
  })

  test('captures the command center', async ({ page }) => {
    await page.goto('/analytics')
    await expect(
      page.getByRole('heading', { name: 'IT command center' }),
    ).toBeVisible()
    await expect(page.getByText('94.2%')).toBeVisible()
    await capture(page, 'command-center.png')
  })

  test('captures the service desk queue', async ({ page }) => {
    await page.goto('/tickets')
    await expect(
      page.getByRole('heading', { name: 'Support queue' }),
    ).toBeVisible()
    await expect(page.getByRole('link', { name: 'INC-1042' })).toBeVisible()
    await capture(page, 'ticket-queue.png')
  })

  test('captures the immutable audit trail', async ({ page }) => {
    await page.goto('/administration/audit')
    await expect(
      page.getByRole('heading', { name: 'Audit trail' }),
    ).toBeVisible()
    await expect(page.getByText('ticket.priority.changed')).toBeVisible()
    await capture(page, 'audit-trail.png')
  })
})
