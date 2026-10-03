import { z } from 'zod'
import { apiRequest } from '../../api/client'

export const auditSourceSchema = z.enum([
  'ACCESS',
  'DIRECTORY',
  'TICKET',
  'SLA',
  'KNOWLEDGE',
  'ASSET',
  'ALERT',
  'AI',
])

export const auditEventPageSchema = z.object({
  items: z.array(
    z.object({
      id: z.string().uuid(),
      source: auditSourceSchema,
      action: z.string(),
      entity_type: z.string(),
      entity_id: z.string().uuid(),
      actor_id: z.string().uuid().nullable(),
      before_state: z.record(z.string(), z.unknown()).nullable(),
      after_state: z.record(z.string(), z.unknown()).nullable(),
      reason: z.string(),
      request_id: z.string().nullable(),
      created_at: z.string(),
    }),
  ),
  total: z.number().int().nonnegative(),
  offset: z.number().int().nonnegative(),
  limit: z.number().int().positive().max(100),
})

export type AuditPageResult = z.infer<typeof auditEventPageSchema>

export const auditApi = {
  events: (
    token: string | null,
    query: URLSearchParams,
    signal?: AbortSignal,
  ) =>
    apiRequest(
      token,
      `/audit/events?${query}`,
      auditEventPageSchema,
      {},
      signal,
    ),
}
