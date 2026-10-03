import '@testing-library/jest-dom/vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthContext } from '../auth/authContextValue'
import { KnowledgeArticlePage } from './KnowledgeArticlePage'
import { KnowledgePage } from './KnowledgePage'

const userId = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const articleId = '11111111-1111-4111-8111-111111111111'
const categoryId = '22222222-2222-4222-8222-222222222222'
const versionId = '33333333-3333-4333-8333-333333333333'
const category = {
  id: categoryId,
  code: 'NETWORK',
  name: 'Network access',
  description: 'Connectivity guidance',
  is_active: true,
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T10:00:00Z',
}
const person = { id: userId, display_name: 'Taylor Technician' }
const article = {
  id: articleId,
  slug: 'repair-vpn-profile',
  category,
  author: person,
  owner: person,
  status: 'DRAFT',
  tags: ['vpn', 'remote-access'],
  version: {
    id: versionId,
    version: 2,
    title: 'Repair a managed VPN profile',
    summary: 'Restore managed remote access safely.',
    content: 'Disconnect the VPN. Replace the profile. Reconnect and verify.',
    change_summary: 'Added verification',
    author: person,
    created_at: '2026-09-09T11:00:00Z',
  },
  published_version: null,
  published_at: null,
  created_at: '2026-09-09T10:00:00Z',
  updated_at: '2026-09-09T11:00:00Z',
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
  initial = '/knowledge',
) {
  render(
    <AuthContext.Provider
      value={{
        user: {
          ...person,
          email: 'taylor@example.com',
          status: 'ACTIVE',
          roles: ['TECHNICIAN'],
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

it('searches published knowledge and lets an author create a draft', async () => {
  const writes: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input)
      if (init.method === 'POST' && url.endsWith('/knowledge/articles')) {
        writes.push(JSON.parse(String(init.body)))
        return response({
          ...article,
          version: { ...article.version, version: 1 },
        })
      }
      if (url.endsWith('/knowledge/categories')) return response([category])
      if (url.includes('/knowledge/articles?'))
        return response({
          items: [
            {
              ...article,
              status: 'PUBLISHED',
              published_version: 2,
              published_at: '2026-09-09T12:00:00Z',
            },
          ],
          total: 1,
          offset: 0,
          limit: 25,
        })
      throw new Error(`Unhandled URL ${url}`)
    }),
  )
  setup(
    <Routes>
      <Route path="/knowledge" element={<KnowledgePage />} />
      <Route path="/knowledge/:articleId" element={<h1>Draft workspace</h1>} />
    </Routes>,
    ['knowledge:view', 'knowledge:create'],
  )
  expect(await screen.findByText(article.version.title)).toBeVisible()
  await userEvent.type(
    screen.getByPlaceholderText('VPN, email, access…'),
    'VPN',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Create article' }))
  const form = screen
    .getByRole('heading', { name: 'New article draft' })
    .closest('form')!
  await userEvent.type(
    within(form).getByLabelText('Title'),
    'Reset secure Wi-Fi access',
  )
  await userEvent.type(
    within(form).getByLabelText('Slug'),
    'reset-secure-wifi-access',
  )
  await userEvent.selectOptions(
    within(form).getByLabelText('Category'),
    categoryId,
  )
  await userEvent.type(
    within(form).getByLabelText('Summary'),
    'Restore Wi-Fi access safely.',
  )
  await userEvent.type(
    within(form).getByLabelText('Content'),
    'Forget the managed network and enroll the device again.',
  )
  await userEvent.type(within(form).getByLabelText(/Tags/), 'wifi, access')
  await userEvent.click(
    within(form).getByRole('button', { name: 'Save draft' }),
  )
  expect(
    await screen.findByRole('heading', { name: 'Draft workspace' }),
  ).toBeVisible()
  expect(writes[0]).toMatchObject({
    slug: 'reset-secure-wifi-access',
    tags: ['wifi', 'access'],
  })
})

it('shows immutable history and submits an owned draft for review', async () => {
  const writes: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input)
      if (init.method === 'POST' && url.endsWith('/transitions')) {
        writes.push(JSON.parse(String(init.body)))
        return response({ ...article, status: 'IN_REVIEW' })
      }
      if (url.endsWith('/versions')) return response([article.version])
      if (url.endsWith(`/knowledge/articles/${articleId}`))
        return response(article)
      throw new Error(`Unhandled URL ${url}`)
    }),
  )
  setup(
    <Routes>
      <Route path="/knowledge/:articleId" element={<KnowledgeArticlePage />} />
    </Routes>,
    ['knowledge:view', 'knowledge:update'],
    `/knowledge/${articleId}`,
  )
  expect(
    await screen.findByRole('heading', { name: article.version.title }),
  ).toBeVisible()
  expect(await screen.findByText('v2 · Added verification')).toBeVisible()
  await userEvent.selectOptions(screen.getByLabelText('Action'), 'IN_REVIEW')
  await userEvent.type(screen.getByLabelText('Reason'), 'Ready for peer review')
  await userEvent.click(screen.getByRole('button', { name: 'Apply action' }))
  await vi.waitFor(() =>
    expect(writes).toContainEqual({
      status: 'IN_REVIEW',
      reason: 'Ready for peer review',
    }),
  )
})

it('renders a correlated knowledge search failure with retry', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) =>
      String(input).endsWith('/knowledge/categories')
        ? response([])
        : response(
            {
              title: 'Knowledge search unavailable',
              request_id: 'kb-request-9',
            },
            503,
          ),
    ),
  )
  setup(<KnowledgePage />, ['knowledge:view'])
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Knowledge search unavailable (request kb-request-9)',
  )
  expect(screen.getByRole('button', { name: 'Retry' })).toBeVisible()
})

it('indexes the exact published version for AI retrieval', async () => {
  const published = {
    ...article,
    status: 'PUBLISHED',
    published_version: 2,
    published_at: '2026-09-09T12:00:00Z',
  }
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
      const url = String(input)
      if (
        init.method === 'POST' &&
        url.endsWith(`/ai/knowledge/${articleId}/index`)
      )
        return response(
          {
            article_id: articleId,
            version_id: versionId,
            article_version: 2,
            chunks: 3,
            embeddings_created: 3,
            embeddings_reused: 0,
            provider: 'test-provider',
            model: 'test-embedding-v1',
          },
          201,
        )
      if (url.endsWith('/events')) return response([])
      if (url.endsWith('/versions')) return response([article.version])
      if (url.endsWith(`/knowledge/articles/${articleId}`))
        return response(published)
      throw new Error(`Unhandled URL ${url}`)
    }),
  )
  setup(
    <Routes>
      <Route path="/knowledge/:articleId" element={<KnowledgeArticlePage />} />
    </Routes>,
    [
      'knowledge:view',
      'knowledge:update',
      'knowledge:review',
      'knowledge:publish',
    ],
    `/knowledge/${articleId}`,
  )
  await userEvent.click(
    await screen.findByRole('button', { name: 'Index published version' }),
  )
  expect(await screen.findByRole('status')).toHaveTextContent(
    'Version 2: 3 chunks · 3 embedded · 0 reused',
  )
})
