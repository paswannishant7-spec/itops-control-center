import { refreshRequest, logoutRequest } from './authApi'
afterEach(() => vi.unstubAllGlobals())
it('coalesces rotating refresh calls and loads the current permission set', async () => {
  const mocked = vi.fn(async (url: string) => {
    if (url.endsWith('/access/me'))
      return new Response(
        JSON.stringify({
          roles: ['EMPLOYEE'],
          permissions: ['ticket:view_own'],
        }),
      )
    return new Response(
      JSON.stringify({
        access_token: 'signed',
        token_type: 'bearer',
        expires_in: 600,
        user: {
          id: 'a135c9eb-6ae3-467c-a4d0-6ff1ad19459c',
          email: 'employee@example.com',
          display_name: 'Employee',
          status: 'ACTIVE',
        },
      }),
    )
  })
  vi.stubGlobal('fetch', mocked)
  const [one, two] = await Promise.all([refreshRequest(), refreshRequest()])
  expect(one).toEqual(two)
  expect(one.user.permissions).toEqual(['ticket:view_own'])
  expect(mocked).toHaveBeenCalledTimes(2)
})
it('reports logout failure so a live server session is not silently hidden', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response('', { status: 503 })),
  )
  await expect(logoutRequest()).rejects.toThrow('Sign-out failed')
})
