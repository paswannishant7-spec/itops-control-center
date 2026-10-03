import { z } from 'zod'
import { apiBase } from '../features/auth/authApi'

const problemSchema = z.object({
  title: z.string().optional(),
  code: z.string().optional(),
  request_id: z.string().optional(),
  details: z.unknown().optional(),
})

export class ApiProblem extends Error {
  readonly status: number
  readonly code?: string
  readonly requestId?: string
  readonly details?: unknown

  constructor(
    message: string,
    status: number,
    code?: string,
    requestId?: string,
    details?: unknown,
  ) {
    super(message)
    this.name = 'ApiProblem'
    this.status = status
    this.code = code
    this.requestId = requestId
    this.details = details
  }
}

export async function apiRequest<T>(
  accessToken: string | null,
  path: string,
  schema: z.ZodType<T>,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<T> {
  const response = await apiResponse(accessToken, path, init, signal)
  if (response.status === 204) return schema.parse(undefined)
  return schema.parse(await response.json())
}

export async function apiResponse(
  accessToken: string | null,
  path: string,
  init: RequestInit = {},
  signal?: AbortSignal,
): Promise<Response> {
  if (!accessToken) throw new ApiProblem('Authentication required', 401)
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    signal,
    headers: {
      Authorization: `Bearer ${accessToken}`,
      ...(typeof init.body === 'string'
        ? { 'Content-Type': 'application/json' }
        : {}),
      ...init.headers,
    },
  })
  if (!response.ok) {
    const parsed = problemSchema.safeParse(
      await response.json().catch(() => ({})),
    )
    const problem = parsed.success ? parsed.data : {}
    throw new ApiProblem(
      problem.title ?? 'Unable to complete this request',
      response.status,
      problem.code,
      problem.request_id,
      problem.details,
    )
  }
  return response
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiProblem && error.requestId)
    return `${error.message} (request ${error.requestId})`
  return error instanceof Error ? error.message : 'Unexpected request failure'
}
