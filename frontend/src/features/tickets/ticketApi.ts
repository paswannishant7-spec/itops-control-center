import { z } from 'zod'
import { apiRequest, apiResponse } from '../../api/client'

const namedSchema = z.object({ id: z.string().uuid(), name: z.string() })
const personSchema = z.object({
  id: z.string().uuid(),
  display_name: z.string(),
  email: z.string().email(),
})
export const ticketSummarySchema = z.object({
  id: z.string().uuid(),
  reference: z.string(),
  title: z.string(),
  requester: personSchema,
  department: namedSchema.nullable(),
  location: namedSchema.nullable(),
  impact: z.string(),
  urgency: z.string(),
  priority: z.string(),
  sla_state: z.string().nullable().optional(),
  status: z.string(),
  assignment_team: namedSchema.nullable(),
  assigned_technician: personSchema.nullable(),
  record_type: z.string().default('REQUEST'),
  source: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
})
export const ticketDetailSchema = ticketSummarySchema.extend({
  description: z.string(),
  asset_id: z.string().uuid().nullable(),
  category: namedSchema.nullable(),
  subcategory: namedSchema.nullable(),
  first_response_at: z.string().nullable(),
  resolved_at: z.string().nullable(),
  closed_at: z.string().nullable(),
  reopened_at: z.string().nullable(),
  resolution_summary: z.string().nullable(),
  resolution_code: z.string().nullable(),
})
const ticketPageSchema = z.object({
  items: z.array(ticketSummarySchema),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
})
const commentSchema = z.object({
  id: z.string().uuid(),
  author: personSchema,
  body: z.string(),
  visibility: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
})
const commentPageSchema = z.object({
  items: z.array(commentSchema),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
})
const attachmentSchema = z.object({
  id: z.string().uuid(),
  original_name: z.string(),
  content_type: z.string(),
  size_bytes: z.number(),
  uploader: personSchema,
  created_at: z.string(),
})
const eventSchema = z.object({
  id: z.string().uuid(),
  event_type: z.string(),
  actor: personSchema,
  before_state: z.record(z.string(), z.unknown()).nullable(),
  after_state: z.record(z.string(), z.unknown()).nullable(),
  reason: z.string(),
  created_at: z.string(),
})
const eventPageSchema = z.object({
  items: z.array(eventSchema),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
})
const slaSchema = z
  .object({
    instance_id: z.string().uuid(),
    policy_name: z.string(),
    calendar_name: z.string(),
    calendar_timezone: z.string(),
    state: z.enum(['ON_TRACK', 'AT_RISK', 'BREACHED', 'PAUSED', 'COMPLETED']),
    active_target: z.enum(['RESPONSE', 'RESOLUTION']),
    response_target_seconds: z.number(),
    resolution_target_seconds: z.number(),
    response_elapsed_seconds: z.number(),
    resolution_elapsed_seconds: z.number(),
    elapsed_seconds: z.number(),
    remaining_seconds: z.number(),
    percentage: z.number(),
    is_paused: z.boolean(),
    response_breached_at: z.string().nullable(),
    resolution_breached_at: z.string().nullable(),
    escalated_at: z.string().nullable(),
    last_evaluated_at: z.string().nullable(),
  })
  .nullable()
const classificationOutputSchema = z.object({
  category_id: z.string().uuid().nullable(),
  subcategory_id: z.string().uuid().nullable(),
  category: z.string().nullable(),
  subcategory: z.string().nullable(),
  impact: z.enum(['LOW', 'MEDIUM', 'HIGH']),
  urgency: z.enum(['LOW', 'MEDIUM', 'HIGH']),
  priority_recommendation: z.enum(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']),
  possible_causes: z.array(z.string()),
  recommended_checks: z.array(z.string()),
  confidence: z.number().min(0).max(1),
})
const classificationSchema = z.object({
  interaction_id: z.string().uuid(),
  ticket_id: z.string().uuid(),
  source: z.enum(['MODEL', 'FALLBACK']),
  provider: z.string(),
  model: z.string(),
  status: z.enum(['SUCCEEDED', 'FALLBACK']),
  confidence_band: z.enum(['LOW', 'MODERATE', 'HIGH']),
  fallback_reason: z.string().nullable(),
  recommendation: classificationOutputSchema,
  created_at: z.string(),
})
const troubleshootingOutputSchema = z.object({
  summary: z.string(),
  known_facts: z.array(z.string()),
  possible_causes: z.array(z.string()),
  recommended_actions: z.array(z.string()),
  uncertain_assumptions: z.array(z.string()),
  cited_chunk_ids: z.array(z.string().uuid()),
  confidence: z.number().min(0).max(1),
})
const knowledgeCitationSchema = z.object({
  article_id: z.string().uuid(),
  version_id: z.string().uuid(),
  chunk_id: z.string().uuid(),
  article_slug: z.string(),
  article_title: z.string(),
  article_version: z.number().int().positive(),
  chunk_ordinal: z.number().int().nonnegative(),
  excerpt: z.string(),
  similarity: z.number().min(-1).max(1),
})
const troubleshootingSchema = z.object({
  interaction_id: z.string().uuid(),
  ticket_id: z.string().uuid(),
  source: z.enum(['MODEL', 'FALLBACK']),
  provider: z.string(),
  model: z.string(),
  status: z.enum(['SUCCEEDED', 'FALLBACK']),
  confidence_band: z.enum(['LOW', 'MODERATE', 'HIGH']),
  fallback_reason: z.string().nullable(),
  recommendation: troubleshootingOutputSchema,
  citations: z.array(knowledgeCitationSchema),
  created_at: z.string(),
})
const similarTicketItemSchema = z.object({
  ticket_id: z.string().uuid(),
  reference: z.string(),
  title: z.string(),
  similarity: z.number().min(-1).max(1),
  status: z.enum(['RESOLVED', 'CLOSED']),
  priority: z.string(),
  category: z.string().nullable(),
  subcategory: z.string().nullable(),
  resolution_summary: z.string(),
  resolution_code: z.string().nullable(),
  resolved_at: z.string().nullable(),
  closed_at: z.string().nullable(),
})
const similarTicketResponseSchema = z.object({
  ticket_id: z.string().uuid(),
  provider: z.string(),
  model: z.string(),
  indexed_embeddings: z.number().int().nonnegative(),
  reused_embeddings: z.number().int().nonnegative(),
  items: z.array(similarTicketItemSchema),
})
const feedbackSchema = z.object({
  id: z.string().uuid(),
  interaction_id: z.string().uuid(),
  recommendation_id: z.string().uuid(),
  ticket_id: z.string().uuid(),
  actor_id: z.string().uuid(),
  action: z.enum(['ACCEPTED', 'EDITED', 'REJECTED', 'REGENERATED']),
  feedback_text: z.string().nullable(),
  edited_content: z.string().nullable(),
  confidence: z.number().min(0).max(1),
  output_type: z.string(),
  created_at: z.string(),
})
const assistantBaseSchema = z.object({
  interaction_id: z.string().uuid(),
  recommendation_id: z.string().uuid(),
  ticket_id: z.string().uuid(),
  source: z.enum(['MODEL', 'FALLBACK']),
  provider: z.string(),
  model: z.string(),
  status: z.enum(['SUCCEEDED', 'FALLBACK']),
  confidence_band: z.enum(['LOW', 'MODERATE', 'HIGH']),
  fallback_reason: z.string().nullable(),
  feedback: feedbackSchema.nullable(),
  created_at: z.string(),
})
const responseDraftAssistantSchema = assistantBaseSchema.extend({
  task_type: z.literal('RESPONSE_DRAFT'),
  recommendation: z.object({
    draft: z.string(),
    key_points: z.array(z.string()),
    safety_notes: z.array(z.string()),
    confidence: z.number().min(0).max(1),
  }),
})
const ticketSummaryAssistantSchema = assistantBaseSchema.extend({
  task_type: z.literal('SUMMARIZATION'),
  recommendation: z.object({
    summary: z.string(),
    key_facts: z.array(z.string()),
    open_questions: z.array(z.string()),
    suggested_next_step: z.string(),
    confidence: z.number().min(0).max(1),
  }),
})
const assistantResponseSchema = z.discriminatedUnion('task_type', [
  responseDraftAssistantSchema,
  ticketSummaryAssistantSchema,
])

export type TicketSummary = z.infer<typeof ticketSummarySchema>
export type TicketDetail = z.infer<typeof ticketDetailSchema>
export type TicketComment = z.infer<typeof commentSchema>
export type TicketAttachment = z.infer<typeof attachmentSchema>
export type TicketEvent = z.infer<typeof eventSchema>
export type TicketSla = z.infer<typeof slaSchema>
export type TicketClassification = z.infer<typeof classificationSchema>
export type TicketTroubleshooting = z.infer<typeof troubleshootingSchema>
export type SimilarTicketResponse = z.infer<typeof similarTicketResponseSchema>
export type AssistantTask = 'RESPONSE_DRAFT' | 'SUMMARIZATION'
export type AssistantResponse = z.infer<typeof assistantResponseSchema>
export type FeedbackAction = z.infer<typeof feedbackSchema>['action']

function uploadContentType(file: File) {
  if (file.type) return file.type
  const extension = file.name.split('.').pop()?.toLowerCase()
  return (
    {
      log: 'text/plain',
      md: 'text/markdown',
      csv: 'text/csv',
      json: 'application/json',
    }[extension ?? ''] ?? 'application/octet-stream'
  )
}

export const ticketApi = {
  list: (token: string | null, query: string, signal?: AbortSignal) =>
    apiRequest(token, `/tickets?${query}`, ticketPageSchema, {}, signal),
  get: (token: string | null, id: string, signal?: AbortSignal) =>
    apiRequest(token, `/tickets/${id}`, ticketDetailSchema, {}, signal),
  sla: (token: string | null, id: string, signal?: AbortSignal) =>
    apiRequest(token, `/sla/tickets/${id}`, slaSchema, {}, signal),
  latestClassification: (
    token: string | null,
    id: string,
    signal?: AbortSignal,
  ) =>
    apiRequest(
      token,
      `/ai/tickets/${id}/classifications/latest`,
      classificationSchema.nullable(),
      {},
      signal,
    ),
  classify: (token: string | null, id: string) =>
    apiRequest(
      token,
      `/ai/tickets/${id}/classifications`,
      classificationSchema,
      { method: 'POST' },
    ),
  latestTroubleshooting: (
    token: string | null,
    id: string,
    signal?: AbortSignal,
  ) =>
    apiRequest(
      token,
      `/ai/tickets/${id}/troubleshooting/latest`,
      troubleshootingSchema.nullable(),
      {},
      signal,
    ),
  troubleshoot: (token: string | null, id: string) =>
    apiRequest(
      token,
      `/ai/tickets/${id}/troubleshooting`,
      troubleshootingSchema,
      { method: 'POST' },
    ),
  similar: (token: string | null, id: string) =>
    apiRequest(
      token,
      `/ai/tickets/${id}/similar`,
      similarTicketResponseSchema,
      { method: 'POST' },
    ),
  latestAssistant: (
    token: string | null,
    id: string,
    task: AssistantTask,
    signal?: AbortSignal,
  ) =>
    apiRequest(
      token,
      `/ai/tickets/${id}/assistant/${task}/latest`,
      assistantResponseSchema.nullable(),
      {},
      signal,
    ),
  generateAssistant: (token: string | null, id: string, task: AssistantTask) =>
    apiRequest(
      token,
      `/ai/tickets/${id}/assistant/${task}`,
      assistantResponseSchema,
      { method: 'POST' },
    ),
  reviewRecommendation: (
    token: string | null,
    ticketId: string,
    recommendationId: string,
    body: {
      action: FeedbackAction
      feedback_text?: string
      edited_content?: string
    },
  ) =>
    apiRequest(
      token,
      `/ai/tickets/${ticketId}/recommendations/${recommendationId}/feedback`,
      feedbackSchema,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  create: (token: string | null, body: object) =>
    apiRequest(token, '/tickets', ticketDetailSchema, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  update: (token: string | null, id: string, body: object) =>
    apiRequest(token, `/tickets/${id}`, ticketDetailSchema, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  assign: (token: string | null, id: string, body: object) =>
    apiRequest(token, `/tickets/${id}/assignment`, ticketDetailSchema, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  transition: (token: string | null, id: string, body: object) =>
    apiRequest(token, `/tickets/${id}/transitions`, ticketDetailSchema, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  comments: (token: string | null, id: string, signal?: AbortSignal) =>
    apiRequest(
      token,
      `/tickets/${id}/comments?limit=100`,
      commentPageSchema,
      {},
      signal,
    ),
  addComment: (token: string | null, id: string, body: object) =>
    apiRequest(token, `/tickets/${id}/comments`, commentSchema, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  attachments: (token: string | null, id: string, signal?: AbortSignal) =>
    apiRequest(
      token,
      `/tickets/${id}/attachments`,
      z.array(attachmentSchema),
      {},
      signal,
    ),
  upload: (token: string | null, id: string, file: File) =>
    apiRequest(
      token,
      `/tickets/${id}/attachments?filename=${encodeURIComponent(file.name)}`,
      attachmentSchema,
      {
        method: 'POST',
        headers: { 'Content-Type': uploadContentType(file) },
        body: file,
      },
    ),
  download: async (
    token: string | null,
    ticketId: string,
    attachmentId: string,
  ) => {
    const response = await apiResponse(
      token,
      `/tickets/${ticketId}/attachments/${attachmentId}`,
    )
    return response.blob()
  },
  events: (token: string | null, id: string, signal?: AbortSignal) =>
    apiRequest(
      token,
      `/tickets/${id}/events?limit=100`,
      eventPageSchema,
      {},
      signal,
    ),
}
