import { z } from 'zod'
import { apiBase } from '../auth/authApi'

export const realtimeTopicSchema = z.enum([
  'tickets',
  'sla',
  'alerts',
  'notifications',
  'devices',
  'access',
])

export const realtimeMessageSchema = z.discriminatedUnion('type', [
  z.object({
    type: z.literal('ready'),
    protocol: z.literal(1),
    cursor: z.number().int().nonnegative(),
    topics: z.array(realtimeTopicSchema),
    heartbeat_seconds: z.number().positive(),
  }),
  z.object({
    type: z.literal('invalidate'),
    sequence: z.number().int().positive(),
    topic: realtimeTopicSchema.exclude(['access']),
    resource_id: z.string().uuid().nullable(),
  }),
  z.object({
    type: z.literal('resync'),
    reason: z.enum(['backlog', 'access_changed']),
    cursor: z.number().int().nonnegative(),
  }),
  z.object({ type: z.literal('ping') }),
])

export type RealtimeTopic = z.infer<typeof realtimeTopicSchema>

export function realtimeUrl(base = apiBase): string {
  const url = new URL(base, window.location.origin)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  url.pathname = `${url.pathname.replace(/\/$/, '')}/realtime/ws`
  url.search = ''
  url.hash = ''
  return url.toString()
}

export const topicQueryKeys: Record<
  Exclude<RealtimeTopic, 'access'>,
  string[]
> = {
  tickets: [
    'tickets',
    'ticket',
    'ticket-comments',
    'ticket-events',
    'ticket-attachments',
    'analytics-dashboard',
  ],
  sla: ['ticket-sla', 'tickets', 'ticket', 'analytics-dashboard'],
  alerts: [
    'alerts',
    'alert-policies',
    'automation-rules',
    'analytics-dashboard',
  ],
  notifications: ['notifications'],
  devices: ['monitoring-agents', 'asset', 'assets', 'analytics-dashboard'],
}
