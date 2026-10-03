import { z } from 'zod'

const userSchema = z.object({
  id: z.string().uuid(),
  email: z.string().email(),
  display_name: z.string(),
  status: z.string(),
  employee_number: z.string().nullable().optional(),
  job_title: z.string().nullable().optional(),
  department_id: z.string().uuid().nullable().optional(),
  location_id: z.string().uuid().nullable().optional(),
  roles: z.array(z.string()).default([]),
  permissions: z.array(z.string()).default([]),
})
const tokenSchema = z.object({
  access_token: z.string(),
  token_type: z.literal('bearer'),
  expires_in: z.number(),
  user: userSchema,
})

export type AuthUser = z.infer<typeof userSchema>
export type TokenResponse = z.infer<typeof tokenSchema>

export const apiBase =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

async function authRequest(
  path: string,
  init: RequestInit = {},
): Promise<TokenResponse> {
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...init.headers },
  })
  if (!response.ok)
    throw new Error(
      response.status === 401
        ? 'Invalid email or password'
        : 'Authentication service is unavailable',
    )
  const result = tokenSchema.parse(await response.json())
  const grantsResponse = await fetch(`${apiBase}/access/me`, {
    headers: { Authorization: `Bearer ${result.access_token}` },
  })
  if (!grantsResponse.ok)
    throw new Error('Could not load your access permissions')
  const grants = z
    .object({ roles: z.array(z.string()), permissions: z.array(z.string()) })
    .parse(await grantsResponse.json())
  return { ...result, user: { ...result.user, ...grants } }
}

export function loginRequest(email: string, password: string) {
  return authRequest('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

let pendingRefresh: Promise<TokenResponse> | null = null
export function refreshRequest() {
  // StrictMode and concurrent consumers share one rotating-cookie request.
  pendingRefresh ??= authRequest('/auth/refresh', { method: 'POST' }).finally(
    () => {
      pendingRefresh = null
    },
  )
  return pendingRefresh
}

export async function logoutRequest(): Promise<void> {
  const response = await fetch(`${apiBase}/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) throw new Error('Sign-out failed. Please retry.')
}
