import { z } from 'zod'
import { apiRequest } from '../../api/client'

const matrixEntry = z.object({
  impact: z.string(),
  urgency: z.string(),
  priority: z.string(),
})
const windowSchema = z.object({
  weekday: z.number(),
  start_minute: z.number(),
  end_minute: z.number(),
})
const holidaySchema = z.object({ holiday_date: z.string(), name: z.string() })
const calendarSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  timezone: z.string(),
  is_active: z.boolean(),
  is_default: z.boolean(),
  windows: z.array(windowSchema),
  holidays: z.array(holidaySchema),
  created_at: z.string(),
  updated_at: z.string(),
})
const policySchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  priority: z.string(),
  calendar_id: z.string().uuid(),
  response_target_minutes: z.number(),
  resolution_target_minutes: z.number(),
  at_risk_percent: z.number(),
  is_active: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
})

export type MatrixEntry = z.infer<typeof matrixEntry>
export type BusinessCalendar = z.infer<typeof calendarSchema>
export type SlaPolicy = z.infer<typeof policySchema>

export const slaApi = {
  matrix: (token: string | null, signal?: AbortSignal) =>
    apiRequest(token, '/sla/priority-matrix', z.array(matrixEntry), {}, signal),
  setMatrix: (
    token: string | null,
    impact: string,
    urgency: string,
    priority: string,
  ) =>
    apiRequest(
      token,
      `/sla/priority-matrix/${impact}/${urgency}`,
      matrixEntry,
      {
        method: 'PUT',
        body: JSON.stringify({ priority }),
      },
    ),
  calendars: (token: string | null, signal?: AbortSignal) =>
    apiRequest(token, '/sla/calendars', z.array(calendarSchema), {}, signal),
  createCalendar: (token: string | null, body: object) =>
    apiRequest(token, '/sla/calendars', calendarSchema, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  policies: (token: string | null, signal?: AbortSignal) =>
    apiRequest(token, '/sla/policies', z.array(policySchema), {}, signal),
  createPolicy: (token: string | null, body: object) =>
    apiRequest(token, '/sla/policies', policySchema, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
}
