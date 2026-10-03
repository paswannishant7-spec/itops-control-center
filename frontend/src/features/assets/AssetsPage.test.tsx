import '@testing-library/jest-dom/vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AuthContext } from '../auth/authContextValue'
import { AssetsPage } from './AssetsPage'

const assetId = '11111111-1111-4111-8111-111111111111'

function response(value: unknown) {
  return new Response(JSON.stringify(value), {
    headers: { 'Content-Type': 'application/json' },
  })
}

it('shows scoped assets and submits a new inventory record', async () => {
  const writes: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_input: RequestInfo | URL, init: RequestInit = {}) => {
      const asset = {
        id: assetId,
        asset_tag: 'LT-1001',
        serial_number: 'SN-1001',
        hostname: 'support-laptop',
        asset_type: 'LAPTOP',
        manufacturer: 'Framework',
        model: 'Laptop 13',
        operating_system: 'Windows 11',
        ip_address: null,
        mac_address: null,
        owner: null,
        department: null,
        location: null,
        purchase_date: null,
        warranty_end: null,
        status: 'ACTIVE',
        last_seen: null,
        health_status: 'HEALTHY',
        created_at: '2026-09-12T10:00:00Z',
        updated_at: '2026-09-12T10:00:00Z',
      }
      if (init.method === 'POST') {
        writes.push(JSON.parse(String(init.body)))
        return response(asset)
      }
      return response({ items: [asset], total: 1, offset: 0, limit: 50 })
    }),
  )
  render(
    <AuthContext.Provider
      value={{
        user: {
          id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
          display_name: 'Asset Administrator',
          email: 'admin@example.com',
          status: 'ACTIVE',
          roles: ['ADMIN'],
          permissions: ['asset:view_all', 'asset:create'],
        },
        accessToken: 'signed-token',
        loading: false,
        login: async () => {},
        logout: async () => {},
      }}
    >
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <AssetsPage />
        </MemoryRouter>
      </QueryClientProvider>
    </AuthContext.Provider>,
  )
  expect(await screen.findByText('LT-1001')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Register asset' }))
  await userEvent.type(screen.getByLabelText('Asset tag'), 'LT-2002')
  await userEvent.type(
    screen.getByLabelText('Reason'),
    'Add purchased hardware',
  )
  await userEvent.click(screen.getByRole('button', { name: 'Register asset' }))
  expect(writes).toContainEqual(
    expect.objectContaining({
      asset_tag: 'LT-2002',
      asset_type: 'LAPTOP',
      reason: 'Add purchased hardware',
    }),
  )
})
