import { z } from 'zod'
import { apiRequest } from '../../api/client'

const volumePointSchema = z.object({
  period_start: z.string(),
  created: z.number().int().nonnegative(),
  resolved: z.number().int().nonnegative(),
})
const breakdownSchema = z.object({
  label: z.string(),
  count: z.number().int().nonnegative(),
})
const durationSchema = z.object({
  minutes: z.number().nonnegative().nullable(),
  sample_size: z.number().int().nonnegative(),
})
const percentageSchema = z.object({
  percent: z.number().min(0).max(100).nullable(),
  sample_size: z.number().int().nonnegative(),
})

export const dashboardSchema = z.object({
  generated_at: z.string(),
  scope: z.object({
    audience: z.enum(['TEAM', 'ORGANIZATION']),
    label: z.string(),
    window_days: z.number().int().min(7).max(365),
    window_start: z.string(),
    window_end: z.string(),
  }),
  summary: z.object({
    open_tickets: z.number().int().nonnegative(),
    assigned_to_me: z.number().int().nonnegative(),
    unassigned_tickets: z.number().int().nonnegative(),
    active_incidents: z.number().int().nonnegative(),
    critical_incidents: z.number().int().nonnegative(),
    sla_at_risk: z.number().int().nonnegative(),
    sla_breached: z.number().int().nonnegative(),
    online_devices: z.number().int().nonnegative(),
    offline_devices: z.number().int().nonnegative(),
    unhealthy_devices: z.number().int().nonnegative(),
    critical_alerts: z.number().int().nonnegative(),
  }),
  performance: z.object({
    mttr: durationSchema,
    mtta: durationSchema,
    sla_compliance: percentageSchema,
    first_contact_resolution_proxy: percentageSchema,
    reopen_rate: percentageSchema,
  }),
  ticket_volume: z.object({
    daily: z.array(volumePointSchema),
    weekly: z.array(volumePointSchema),
    monthly: z.array(volumePointSchema),
  }),
  by_category: z.array(breakdownSchema),
  by_department: z.array(breakdownSchema),
  by_priority: z.array(breakdownSchema),
  technician_workload: z.array(
    z.object({
      technician_id: z.string().uuid(),
      technician_name: z.string(),
      assigned_open: z.number().int().nonnegative(),
      resolved_in_window: z.number().int().nonnegative(),
    }),
  ),
  recurring_issues: z.array(
    z.object({
      category: z.string(),
      subcategory: z.string().nullable(),
      ticket_count: z.number().int().min(2),
    }),
  ),
  asset_incident_frequency: z.array(
    z.object({
      asset_id: z.string().uuid(),
      asset_tag: z.string(),
      incident_count: z.number().int().positive(),
    }),
  ),
  ai_assistance: z.object({
    reviewed_recommendations: z.number().int().nonnegative(),
    accepted: z.number().int().nonnegative(),
    edited: z.number().int().nonnegative(),
    rejected: z.number().int().nonnegative(),
    regenerated: z.number().int().nonnegative(),
    acceptance_rate: z.number().min(0).max(100).nullable(),
    edit_rate: z.number().min(0).max(100).nullable(),
    rejection_rate: z.number().min(0).max(100).nullable(),
    label: z.string(),
  }),
  attention: z.object({
    urgent_tickets: z.array(
      z.object({
        id: z.string().uuid(),
        reference: z.string(),
        title: z.string(),
        priority: z.string(),
        status: z.string(),
        sla_state: z.string().nullable(),
        updated_at: z.string(),
      }),
    ),
    device_health_issues: z.array(
      z.object({
        agent_id: z.string().uuid(),
        asset_id: z.string().uuid(),
        asset_tag: z.string(),
        hostname: z.string().nullable(),
        status: z.string(),
        health_status: z.string(),
      }),
    ),
    critical_alerts: z.array(
      z.object({
        id: z.string().uuid(),
        asset_id: z.string().uuid(),
        asset_tag: z.string(),
        severity: z.string(),
        metric: z.string(),
        state: z.string(),
        triggered_at: z.string(),
      }),
    ),
  }),
})

export type Dashboard = z.infer<typeof dashboardSchema>
export type VolumePoint = z.infer<typeof volumePointSchema>

export const analyticsApi = {
  dashboard: (token: string | null, days: number, signal?: AbortSignal) =>
    apiRequest(
      token,
      `/analytics/dashboard?window_days=${days}`,
      dashboardSchema,
      {},
      signal,
    ),
}
