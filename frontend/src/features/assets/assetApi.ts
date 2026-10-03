import { z } from 'zod'
import { apiRequest } from '../../api/client'

const referenceSchema = z.object({
  id: z.string().uuid(),
  code: z.string(),
  name: z.string(),
})
const ownerSchema = z.object({
  id: z.string().uuid(),
  display_name: z.string(),
  email: z.string().email(),
})
export const assetSchema = z.object({
  id: z.string().uuid(),
  asset_tag: z.string(),
  serial_number: z.string().nullable(),
  hostname: z.string().nullable(),
  asset_type: z.string(),
  manufacturer: z.string().nullable(),
  model: z.string().nullable(),
  operating_system: z.string().nullable(),
  ip_address: z.string().nullable(),
  mac_address: z.string().nullable(),
  owner: ownerSchema.nullable(),
  department: referenceSchema.nullable(),
  location: referenceSchema.nullable(),
  purchase_date: z.string().nullable(),
  warranty_end: z.string().nullable(),
  status: z.string(),
  last_seen: z.string().nullable(),
  health_status: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
})
const assetPageSchema = z.object({
  items: z.array(assetSchema),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
})
const assignmentSchema = z.object({
  id: z.string().uuid(),
  owner: ownerSchema.nullable(),
  department: referenceSchema.nullable(),
  location: referenceSchema.nullable(),
  assigned_by: ownerSchema,
  reason: z.string(),
  started_at: z.string(),
  ended_at: z.string().nullable(),
})
const eventSchema = z.object({
  id: z.string().uuid(),
  action: z.string(),
  actor: ownerSchema,
  before_state: z.record(z.string(), z.unknown()).nullable(),
  after_state: z.record(z.string(), z.unknown()).nullable(),
  reason: z.string(),
  created_at: z.string(),
})
const historySchema = z.object({
  assignments: z.array(assignmentSchema),
  events: z.array(eventSchema),
})
const ticketSchema = z.object({
  id: z.string().uuid(),
  reference: z.string(),
  title: z.string(),
  status: z.string(),
  priority: z.string(),
  updated_at: z.string(),
})

export type Asset = z.infer<typeof assetSchema>

export const assetApi = {
  list: (token: string | null, query: string, signal?: AbortSignal) =>
    apiRequest(token, `/assets?${query}`, assetPageSchema, {}, signal),
  detail: (token: string | null, id: string, signal?: AbortSignal) =>
    apiRequest(token, `/assets/${id}`, assetSchema, {}, signal),
  create: (token: string | null, body: object) =>
    apiRequest(token, '/assets', assetSchema, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  update: (token: string | null, id: string, body: object) =>
    apiRequest(token, `/assets/${id}`, assetSchema, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  assign: (token: string | null, id: string, body: object) =>
    apiRequest(token, `/assets/${id}/assignments`, assetSchema, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  retire: (token: string | null, id: string, reason: string) =>
    apiRequest(token, `/assets/${id}/retire`, assetSchema, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  history: (token: string | null, id: string, signal?: AbortSignal) =>
    apiRequest(token, `/assets/${id}/history`, historySchema, {}, signal),
  tickets: (token: string | null, id: string, signal?: AbortSignal) =>
    apiRequest(
      token,
      `/assets/${id}/tickets`,
      z.array(ticketSchema),
      {},
      signal,
    ),
}
