import '@testing-library/jest-dom/vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen } from '@testing-library/react'
import { AuthContext } from '../auth/authContextValue'
import type { AuthUser } from '../auth/authApi'
import { realtimeUrl } from './realtime'
import { RealtimeProvider } from './RealtimeProvider'

class FakeWebSocket {
  static readonly OPEN = 1
  static readonly instances: FakeWebSocket[] = []
  readonly url: string
  readonly sent: string[] = []
  readyState = 0
  closeCode: number | null = null
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: ((event: { code: number }) => void) | null = null
  onerror: (() => void) | null = null

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  send(value: string) {
    this.sent.push(value)
  }

  open() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  message(value: object) {
    this.onmessage?.({ data: JSON.stringify(value) })
  }

  close(code = 1000) {
    this.readyState = 3
    this.closeCode = code
    this.onclose?.({ code })
  }
}

const user: AuthUser = {
  id: '789496cb-bf60-4502-89a4-eedff21d0712',
  email: 'operator@example.com',
  display_name: 'Operator',
  status: 'ACTIVE',
  roles: ['TECHNICIAN'],
  permissions: ['ticket:view_team', 'alert:view', 'monitoring:view'],
}

function setup() {
  FakeWebSocket.instances.length = 0
  vi.stubGlobal('WebSocket', FakeWebSocket)
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const invalidations = vi.spyOn(client, 'invalidateQueries')
  const refresh = vi.fn(async () => undefined)
  const view = render(
    <QueryClientProvider client={client}>
      <AuthContext.Provider
        value={{
          user,
          accessToken: 'memory-only-access-token',
          loading: false,
          refresh,
          login: vi.fn(),
          logout: vi.fn(),
        }}
      >
        <RealtimeProvider>
          <main>Operations</main>
        </RealtimeProvider>
      </AuthContext.Provider>
    </QueryClientProvider>,
  )
  return { client, invalidations, refresh, view }
}

test('derives secure and same-origin websocket URLs from the API boundary', () => {
  expect(realtimeUrl('/api/v1')).toBe('ws://localhost:3000/api/v1/realtime/ws')
  expect(realtimeUrl('https://support.example.test/api/v1')).toBe(
    'wss://support.example.test/api/v1/realtime/ws',
  )
})

test('authenticates in the first frame and invalidates targeted queries', async () => {
  const { invalidations, view } = setup()
  const socket = FakeWebSocket.instances[0]
  expect(socket.url).toBe('ws://localhost:8000/api/v1/realtime/ws')
  expect(socket.url).not.toContain('memory-only-access-token')
  act(() => socket.open())
  expect(JSON.parse(socket.sent[0])).toEqual({
    type: 'authenticate',
    access_token: 'memory-only-access-token',
  })
  act(() =>
    socket.message({
      type: 'ready',
      protocol: 1,
      cursor: 0,
      topics: ['tickets', 'sla', 'alerts', 'notifications', 'devices'],
      heartbeat_seconds: 20,
    }),
  )
  expect(screen.getByRole('status')).toHaveTextContent('Live updates connected')
  invalidations.mockClear()
  act(() =>
    socket.message({
      type: 'invalidate',
      sequence: 1,
      topic: 'tickets',
      resource_id: '11111111-1111-4111-8111-111111111111',
    }),
  )
  await act(() => new Promise((resolve) => window.setTimeout(resolve, 100)))
  expect(invalidations).toHaveBeenCalledWith({ queryKey: ['tickets'] })
  expect(invalidations).toHaveBeenCalledWith({ queryKey: ['ticket-comments'] })
  act(() => socket.message({ type: 'ping' }))
  expect(JSON.parse(socket.sent.at(-1)!)).toEqual({ type: 'pong' })
  view.unmount()
  expect(socket.closeCode).toBe(1000)
})

test('ignores duplicate frames and refreshes authentication after access changes', () => {
  const { invalidations, refresh } = setup()
  const socket = FakeWebSocket.instances[0]
  act(() => socket.open())
  act(() =>
    socket.message({
      type: 'ready',
      protocol: 1,
      cursor: 7,
      topics: ['notifications'],
      heartbeat_seconds: 20,
    }),
  )
  invalidations.mockClear()
  act(() =>
    socket.message({
      type: 'invalidate',
      sequence: 7,
      topic: 'notifications',
      resource_id: null,
    }),
  )
  act(() => socket.message({ type: 'unknown', payload: 'ignored' }))
  expect(invalidations).not.toHaveBeenCalled()
  act(() =>
    socket.message({
      type: 'resync',
      reason: 'access_changed',
      cursor: 8,
    }),
  )
  expect(refresh).toHaveBeenCalledOnce()
  expect(invalidations).toHaveBeenCalledOnce()
})

test('shows reconnect and paused states for transport and authorization closes', () => {
  const firstSetup = setup()
  const first = FakeWebSocket.instances[0]
  act(() => first.close(1006))
  expect(screen.getByRole('status')).toHaveTextContent(
    'Reconnecting live updates',
  )
  firstSetup.view.unmount()

  const secondSetup = setup()
  const second = FakeWebSocket.instances[0]
  act(() => second.close(4401))
  expect(screen.getAllByRole('status').at(-1)).toHaveTextContent(
    'Live updates paused',
  )
  expect(secondSetup.refresh).toHaveBeenCalledOnce()
})
