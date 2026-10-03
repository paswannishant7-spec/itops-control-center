import { z } from 'zod'
import { apiRequest } from '../../api/client'

export const agentSchema = z.object({
  agent_id: z.string().uuid(),
  device_id: z.string().uuid(),
  asset_tag: z.string(),
  hostname: z.string().nullable(),
  status: z.string(),
  credential_status: z.string(),
  credential_prefix: z.string().nullable(),
  last_seen: z.string().nullable(),
  last_heartbeat: z.string().nullable(),
  missed_heartbeat_count: z.number().int().nonnegative(),
  agent_version: z.string().nullable(),
  enrolled_at: z.string().nullable(),
})
const agentPageSchema = z.object({
  items: z.array(agentSchema),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
})
const enrollmentSchema = z.object({
  agent_id: z.string().uuid(),
  device_id: z.string().uuid(),
  enrollment_token: z.string(),
  expires_at: z.string(),
})
const metricSchema = z.object({
  id: z.string().uuid(),
  sampled_at: z.string(),
  received_at: z.string(),
  cpu_percent: z.number(),
  memory_percent: z.number(),
  memory_used_bytes: z.number(),
  memory_total_bytes: z.number(),
  disk_percent: z.number(),
  disk_used_bytes: z.number(),
  disk_total_bytes: z.number(),
  network_bytes_sent: z.number(),
  network_bytes_received: z.number(),
})
const metricPageSchema = z.object({
  items: z.array(metricSchema),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
})

export type Enrollment = z.infer<typeof enrollmentSchema>

export const monitoringApi = {
  agents: (token: string | null, query: string, signal?: AbortSignal) =>
    apiRequest(
      token,
      `/monitoring/agents?${query}`,
      agentPageSchema,
      {},
      signal,
    ),
  metrics: (token: string | null, id: string, signal?: AbortSignal) =>
    apiRequest(
      token,
      `/monitoring/agents/${id}/metrics?offset=0&limit=100`,
      metricPageSchema,
      {},
      signal,
    ),
  createEnrollment: (token: string | null, body: object) =>
    apiRequest(token, '/monitoring/enrollments', enrollmentSchema, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  disable: (token: string | null, id: string, reason: string) =>
    apiRequest(token, `/monitoring/agents/${id}/disable`, agentSchema, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
}
