import { expect, test, type Page, type Route } from '@playwright/test'

const userId = '73bb9477-5b69-4ee5-aacf-e80ed38a2520'
const ticketId = '63bb9477-5b69-4ee5-aacf-e80ed38a2520'
const eventId = '53bb9477-5b69-4ee5-aacf-e80ed38a2520'

const corsHeaders = {
  'access-control-allow-origin': 'http://127.0.0.1:4173',
  'access-control-allow-credentials': 'true',
  'access-control-allow-headers': 'authorization,content-type',
  'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
  'content-type': 'application/json',
}

const grants = [
  'ticket:create',
  'ticket:view_all',
  'asset:view_all',
  'analytics:view',
  'audit:view',
]

function tokenResponse() {
  return {
    access_token: 'browser-e2e-access-token',
    token_type: 'bearer',
    expires_in: 600,
    user: {
      id: userId,
      email: 'admin@example.test',
      display_name: 'E2E Administrator',
      status: 'ACTIVE',
      roles: ['ADMIN'],
      permissions: grants,
    },
  }
}

async function json(route: Route, status: number, body: object) {
  await route.fulfill({
    status,
    headers: corsHeaders,
    body: JSON.stringify(body),
  })
}

async function mockApi(
  page: Page,
  options: { refreshAuthenticated?: boolean; rejectLogin?: boolean } = {},
) {
  const observedQueries: string[] = []
  await page.route('http://localhost:8000/api/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (request.method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: corsHeaders })
      return
    }
    if (url.pathname.endsWith('/auth/refresh')) {
      if (options.refreshAuthenticated) await json(route, 200, tokenResponse())
      else await json(route, 401, { title: 'Invalid session' })
      return
    }
    if (url.pathname.endsWith('/auth/login')) {
      if (options.rejectLogin)
        await json(route, 401, { title: 'Invalid credentials' })
      else await json(route, 200, tokenResponse())
      return
    }
    if (url.pathname.endsWith('/auth/logout')) {
      await json(route, 200, { message: 'Logged out' })
      return
    }
    if (url.pathname.endsWith('/access/me')) {
      await json(route, 200, { roles: ['ADMIN'], permissions: grants })
      return
    }
    if (url.pathname.endsWith('/tickets')) {
      observedQueries.push(url.search)
      await json(route, 200, {
        items: [
          {
            id: ticketId,
            reference: 'INC-E2E-001',
            title: 'VPN access is unavailable',
            requester: {
              id: userId,
              display_name: 'E2E Administrator',
              email: 'admin@example.test',
            },
            department: null,
            location: null,
            impact: 'HIGH',
            urgency: 'HIGH',
            priority: 'CRITICAL',
            sla_state: 'AT_RISK',
            status: 'OPEN',
            assignment_team: null,
            assigned_technician: null,
            record_type: 'INCIDENT',
            source: 'PORTAL',
            created_at: '2026-09-17T08:00:00Z',
            updated_at: '2026-09-17T08:05:00Z',
          },
        ],
        total: 1,
        offset: 0,
        limit: 25,
      })
      return
    }
    if (url.pathname.endsWith('/assets')) {
      await json(route, 200, { items: [], total: 0, offset: 0, limit: 100 })
      return
    }
    if (url.pathname.endsWith('/audit/events')) {
      await json(route, 200, {
        items: [
          {
            id: eventId,
            source: 'TICKET',
            action: 'ticket.updated',
            entity_type: 'TICKET',
            entity_id: ticketId,
            actor_id: userId,
            before_state: { priority: 'HIGH' },
            after_state: { priority: 'CRITICAL', api_key: '[REDACTED]' },
            reason: 'Impact confirmed',
            request_id: 'e2e-request-1',
            created_at: '2026-09-17T08:05:00Z',
          },
        ],
        total: 1,
        offset: 0,
        limit: 50,
      })
      return
    }
    await json(route, 404, { title: `Unmocked API request: ${url.pathname}` })
  })
  return observedQueries
}

test('signs in and traverses the permission-aware ticket queue', async ({
  page,
}) => {
  const queries = await mockApi(page)
  await page.goto('/tickets')
  await expect(page).toHaveURL(/\/login$/)
  await page.getByLabel('Work email').fill('admin@example.test')
  await page.getByLabel('Password').fill('Correct-Horse-7!')
  await page.getByRole('button', { name: 'Sign in securely' }).click()

  await expect(page).toHaveURL(/\/$/)
  const openNavigation = page.getByRole('button', { name: 'Open navigation' })
  if ((page.viewportSize()?.width ?? 0) <= 780) {
    await expect(openNavigation).toBeVisible()
    await openNavigation.click()
  }
  await page.getByRole('link', { name: 'Tickets', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Support queue' }),
  ).toBeVisible()
  await expect(page.getByRole('link', { name: 'INC-E2E-001' })).toBeVisible()
  await expect(page.getByText('VPN access is unavailable')).toBeVisible()
  await expect(page.getByText('AT RISK')).toBeVisible()

  await page.getByPlaceholder('Reference, title, or description').fill('VPN')
  await expect
    .poll(() => queries.some((query) => query.includes('search=VPN')))
    .toBe(true)
})

test('ticket queue stays usable at the requested viewport widths', async ({
  page,
}) => {
  await mockApi(page)
  await page.goto('/login')
  await page.getByLabel('Work email').fill('admin@example.test')
  await page.getByLabel('Password').fill('Correct-Horse-7!')
  await page.getByRole('button', { name: 'Sign in securely' }).click()
  await expect(page).toHaveURL(/\/$/)
  const openNavigation = page.getByRole('button', { name: 'Open navigation' })
  if ((page.viewportSize()?.width ?? 0) <= 780) {
    await expect(openNavigation).toBeVisible()
    await openNavigation.click()
  }
  await page.getByRole('link', { name: 'Tickets', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'Support queue' }),
  ).toBeVisible()

  for (const width of [1440, 1280, 1024, 768, 390, 360]) {
    await page.setViewportSize({ width, height: 900 })
    await expect(
      page.getByRole('button', { name: 'Create ticket' }),
    ).toBeVisible()
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    )
    expect(
      overflow,
      `horizontal page overflow at ${width}px`,
    ).toBeLessThanOrEqual(1)
  }

  for (const route of ['Assets', 'Audit']) {
    const openNavigation = page.getByRole('button', { name: 'Open navigation' })
    if ((page.viewportSize()?.width ?? 0) <= 780) {
      await expect(openNavigation).toBeVisible()
      await openNavigation.click()
    }
    await page.getByRole('link', { name: route, exact: true }).click()
    for (const width of [1440, 1280, 1024, 768, 390, 360]) {
      await page.setViewportSize({ width, height: 900 })
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth,
      )
      expect(
        overflow,
        `${route} page overflow at ${width}px`,
      ).toBeLessThanOrEqual(1)
    }
  }
})

test('closed mobile navigation cannot receive keyboard focus', async ({
  page,
}) => {
  await mockApi(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/login')
  await page.getByLabel('Work email').fill('admin@example.test')
  await page.getByLabel('Password').fill('Correct-Horse-7!')
  await page.getByRole('button', { name: 'Sign in securely' }).click()
  await expect(page).toHaveURL(/\/$/)
  const sidebar = page.locator('.app-sidebar')
  await expect(sidebar).not.toHaveClass(/is-open/)
  const hiddenLinkCanFocus = await page.evaluate(() => {
    const link = document.querySelector<HTMLElement>('.app-navigation a')
    link?.focus()
    return document.activeElement === link
  })
  expect(hiddenLinkCanFocus).toBe(false)
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await expect(sidebar).toHaveClass(/is-open/)
  await expect(sidebar.getByRole('link', { name: 'Overview' })).toBeVisible()
  await sidebar.getByRole('button', { name: 'Sign out' }).click()
  await expect(page).toHaveURL(/\/login$/)
})

test('keeps authentication failures controlled', async ({ page }) => {
  await mockApi(page, { rejectLogin: true })
  await page.goto('/login')
  await page.getByLabel('Work email').fill('unknown@example.test')
  await page.getByLabel('Password').fill('Wrong-Password-7!')
  await page.getByRole('button', { name: 'Sign in securely' }).click()
  await expect(page.getByRole('alert')).toHaveText('Invalid email or password')
  await expect(page).toHaveURL(/\/login$/)
})

test('renders the immutable audit trail and redacted change details', async ({
  page,
}) => {
  await mockApi(page, { refreshAuthenticated: true })
  await page.goto('/administration/audit')
  await expect(page.getByRole('heading', { name: 'Audit trail' })).toBeVisible()
  await expect(page.getByText('ticket.updated')).toBeVisible()
  await page.getByText('Inspect').click()
  await expect(page.getByText(/e2e-request-1/)).toBeVisible()
  await expect(page.getByText(/\[REDACTED\]/)).toBeVisible()
})
