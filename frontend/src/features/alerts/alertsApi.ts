import { z } from 'zod'
import { apiRequest } from '../../api/client'

export const alertSchema = z.object({
  id: z.string().uuid(),
  policy_id: z.string().uuid(),
  agent_id: z.string().uuid(),
  asset_id: z.string().uuid(),
  asset_tag: z.string(),
  incident_ticket_id: z.string().uuid().nullable(),
  incident_reference: z.string().nullable(),
  source: z.string(),
  severity: z.string(),
  metric: z.string(),
  threshold: z.number(),
  observed_value: z.number(),
  state: z.string(),
  triggered_at: z.string(),
  last_observed_at: z.string(),
  acknowledged_at: z.string().nullable(),
  resolved_at: z.string().nullable(),
  suppressed_at: z.string().nullable(),
})
const alertPageSchema = z.object({
  items: z.array(alertSchema),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
})
const policySchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  metric: z.string(),
  operator: z.string(),
  threshold: z.number(),
  severity: z.string(),
  enabled: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
})
const policyPageSchema = z.object({
  items: z.array(policySchema),
  total: z.number(),
})
const ruleSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  enabled: z.boolean(),
  source: z.string(),
  minimum_severity: z.string(),
  create_incident: z.boolean(),
  notify_team: z.boolean(),
  assignment_team_id: z.string().uuid().nullable(),
  created_by_id: z.string().uuid(),
  created_at: z.string(),
  updated_at: z.string(),
})
const rulePageSchema = z.object({
  items: z.array(ruleSchema),
  total: z.number(),
})
const notificationSchema = z.object({
  id: z.string().uuid(),
  alert_id: z.string().uuid().nullable(),
  ticket_id: z.string().uuid().nullable(),
  event_type: z.string(),
  title: z.string(),
  body: z.string(),
  read_at: z.string().nullable(),
  created_at: z.string(),
})
const notificationPageSchema = z.object({
  items: z.array(notificationSchema),
  total: z.number(),
  unread: z.number(),
  offset: z.number(),
  limit: z.number(),
})
const preferenceSchema = z.object({
  in_app_enabled: z.boolean(),
  minimum_alert_severity: z.string(),
})

export const alertsApi = {
  alerts: (token: string | null, query: string, signal?: AbortSignal) =>
    apiRequest(token, `/alerts?${query}`, alertPageSchema, {}, signal),
  transition: (
    token: string | null,
    id: string,
    action: string,
    reason: string,
  ) =>
    apiRequest(token, `/alerts/${id}/${action}`, alertSchema, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  policies: (token: string | null, signal?: AbortSignal) =>
    apiRequest(token, '/alerts/policies', policyPageSchema, {}, signal),
  createPolicy: (token: string | null, body: object) =>
    apiRequest(token, '/alerts/policies', policySchema, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  rules: (token: string | null, signal?: AbortSignal) =>
    apiRequest(token, '/automation/rules', rulePageSchema, {}, signal),
  createRule: (token: string | null, body: object) =>
    apiRequest(token, '/automation/rules', ruleSchema, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  notifications: (token: string | null, signal?: AbortSignal) =>
    apiRequest(
      token,
      '/notifications?offset=0&limit=50',
      notificationPageSchema,
      {},
      signal,
    ),
  readNotification: (token: string | null, id: string) =>
    apiRequest(token, `/notifications/${id}/read`, notificationSchema, {
      method: 'POST',
    }),
  preference: (token: string | null, signal?: AbortSignal) =>
    apiRequest(
      token,
      '/notifications/preferences/me',
      preferenceSchema,
      {},
      signal,
    ),
  updatePreference: (token: string | null, body: object) =>
    apiRequest(token, '/notifications/preferences/me', preferenceSchema, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
}
