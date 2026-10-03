import { z } from 'zod'
import { apiRequest } from '../../api/client'

export const articleStatuses = [
  'DRAFT',
  'IN_REVIEW',
  'PUBLISHED',
  'ARCHIVED',
] as const

const personSchema = z.object({
  id: z.string().uuid(),
  display_name: z.string(),
})
export const categorySchema = z.object({
  id: z.string().uuid(),
  code: z.string(),
  name: z.string(),
  description: z.string().nullable(),
  is_active: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
})
export const versionSchema = z.object({
  id: z.string().uuid(),
  version: z.number().int().positive(),
  title: z.string(),
  summary: z.string(),
  content: z.string(),
  change_summary: z.string(),
  author: personSchema,
  created_at: z.string(),
})
export const articleSchema = z.object({
  id: z.string().uuid(),
  slug: z.string(),
  category: categorySchema,
  author: personSchema,
  owner: personSchema,
  status: z.enum(articleStatuses),
  tags: z.array(z.string()),
  version: versionSchema,
  published_version: z.number().int().positive().nullable(),
  published_at: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
})
const pageSchema = z.object({
  items: z.array(articleSchema),
  total: z.number().int().nonnegative(),
  offset: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
})
const eventSchema = z.object({
  id: z.string().uuid(),
  action: z.string(),
  actor: personSchema,
  before_state: z.record(z.string(), z.unknown()).nullable(),
  after_state: z.record(z.string(), z.unknown()).nullable(),
  reason: z.string(),
  created_at: z.string(),
})
const knowledgeIndexSchema = z.object({
  article_id: z.string().uuid(),
  version_id: z.string().uuid(),
  article_version: z.number().int().positive(),
  chunks: z.number().int().positive(),
  embeddings_created: z.number().int().nonnegative(),
  embeddings_reused: z.number().int().nonnegative(),
  provider: z.string(),
  model: z.string(),
})

export type KnowledgeCategory = z.infer<typeof categorySchema>
export type KnowledgeArticle = z.infer<typeof articleSchema>
export type ArticleStatus = (typeof articleStatuses)[number]

export interface ArticleInput {
  title: string
  summary: string
  content: string
  change_summary: string
  category_id?: string
  tags?: string[]
}

export function getCategories(token: string | null, signal?: AbortSignal) {
  return apiRequest(
    token,
    '/knowledge/categories',
    z.array(categorySchema),
    {},
    signal,
  )
}

export function getArticles(
  token: string | null,
  filters: { search?: string; categoryId?: string; status?: string },
  signal?: AbortSignal,
) {
  const query = new URLSearchParams({ limit: '25', offset: '0' })
  if (filters.search) query.set('search', filters.search)
  if (filters.categoryId) query.set('category_id', filters.categoryId)
  if (filters.status) query.set('status', filters.status)
  return apiRequest(
    token,
    `/knowledge/articles?${query}`,
    pageSchema,
    {},
    signal,
  )
}

export function getArticle(
  token: string | null,
  id: string,
  signal?: AbortSignal,
) {
  return apiRequest(
    token,
    `/knowledge/articles/${id}`,
    articleSchema,
    {},
    signal,
  )
}

export function createArticle(
  token: string | null,
  input: ArticleInput & { slug: string; category_id: string },
) {
  return apiRequest(token, '/knowledge/articles', articleSchema, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function createVersion(
  token: string | null,
  id: string,
  input: ArticleInput,
) {
  return apiRequest(
    token,
    `/knowledge/articles/${id}/versions`,
    articleSchema,
    {
      method: 'POST',
      body: JSON.stringify(input),
    },
  )
}

export function transitionArticle(
  token: string | null,
  id: string,
  status: ArticleStatus,
  reason: string,
) {
  return apiRequest(
    token,
    `/knowledge/articles/${id}/transitions`,
    articleSchema,
    {
      method: 'POST',
      body: JSON.stringify({ status, reason }),
    },
  )
}

export function getVersions(
  token: string | null,
  id: string,
  signal?: AbortSignal,
) {
  return apiRequest(
    token,
    `/knowledge/articles/${id}/versions`,
    z.array(versionSchema),
    {},
    signal,
  )
}

export function getEvents(
  token: string | null,
  id: string,
  signal?: AbortSignal,
) {
  return apiRequest(
    token,
    `/knowledge/articles/${id}/events`,
    z.array(eventSchema),
    {},
    signal,
  )
}

export function createCategory(
  token: string | null,
  input: {
    code: string
    name: string
    description: string | null
    is_active: boolean
  },
) {
  return apiRequest(token, '/knowledge/categories', categorySchema, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export function indexArticle(token: string | null, id: string) {
  return apiRequest(token, `/ai/knowledge/${id}/index`, knowledgeIndexSchema, {
    method: 'POST',
  })
}
