import { z } from 'zod'
import { apiRequest } from '../../api/client'

const referenceSummarySchema = z.object({
  id: z.string().uuid(),
  code: z.string(),
  name: z.string(),
})
export const departmentSchema = referenceSummarySchema.extend({
  description: z.string().nullable(),
  status: z.string(),
  user_count: z.number(),
  team_count: z.number(),
  created_at: z.string(),
  updated_at: z.string(),
})
export const locationSchema = referenceSummarySchema.extend({
  timezone: z.string(),
  address: z.string().nullable(),
  status: z.string(),
  user_count: z.number(),
  team_count: z.number(),
  created_at: z.string(),
  updated_at: z.string(),
})
export const memberSchema = z.object({
  user_id: z.string().uuid(),
  display_name: z.string(),
  email: z.string().email(),
  job_title: z.string().nullable(),
  status: z.string(),
  member_role: z.string(),
  roles: z.array(z.string()),
})
export const teamSchema = referenceSummarySchema.extend({
  description: z.string().nullable(),
  status: z.string(),
  department: referenceSummarySchema.nullable(),
  location: referenceSummarySchema.nullable(),
  member_count: z.number(),
  created_at: z.string(),
  updated_at: z.string(),
})
export const teamDetailSchema = teamSchema.extend({
  members: z.array(memberSchema),
})
export const technicianSchema = z.object({
  id: z.string().uuid(),
  display_name: z.string(),
  email: z.string().email(),
  job_title: z.string().nullable(),
  roles: z.array(z.string()),
})
export const directoryUserSchema = z.object({
  id: z.string().uuid(),
  email: z.string().email(),
  display_name: z.string(),
  employee_number: z.string().nullable(),
  job_title: z.string().nullable(),
  status: z.string(),
  department: referenceSummarySchema.nullable(),
  location: referenceSummarySchema.nullable(),
  roles: z.array(z.string()),
  teams: z.array(referenceSummarySchema),
  last_login_at: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
})
export const userPageSchema = z.object({
  items: z.array(directoryUserSchema),
  total: z.number(),
  offset: z.number(),
  limit: z.number(),
})

export type Department = z.infer<typeof departmentSchema>
export type Location = z.infer<typeof locationSchema>
export type Team = z.infer<typeof teamSchema>
export type TeamDetail = z.infer<typeof teamDetailSchema>
export type DirectoryUser = z.infer<typeof directoryUserSchema>

export const directoryApi = {
  departments: (token: string | null, signal?: AbortSignal) =>
    apiRequest(
      token,
      '/directory/departments',
      z.array(departmentSchema),
      {},
      signal,
    ),
  createDepartment: (token: string | null, body: object) =>
    apiRequest(token, '/directory/departments', departmentSchema, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateDepartment: (token: string | null, id: string, body: object) =>
    apiRequest(token, `/directory/departments/${id}`, departmentSchema, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  locations: (token: string | null, signal?: AbortSignal) =>
    apiRequest(
      token,
      '/directory/locations',
      z.array(locationSchema),
      {},
      signal,
    ),
  createLocation: (token: string | null, body: object) =>
    apiRequest(token, '/directory/locations', locationSchema, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateLocation: (token: string | null, id: string, body: object) =>
    apiRequest(token, `/directory/locations/${id}`, locationSchema, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  teams: (token: string | null, signal?: AbortSignal) =>
    apiRequest(token, '/directory/teams', z.array(teamSchema), {}, signal),
  team: (token: string | null, id: string, signal?: AbortSignal) =>
    apiRequest(token, `/directory/teams/${id}`, teamDetailSchema, {}, signal),
  createTeam: (token: string | null, body: object) =>
    apiRequest(token, '/directory/teams', teamSchema, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateTeam: (token: string | null, id: string, body: object) =>
    apiRequest(token, `/directory/teams/${id}`, teamSchema, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  candidates: (
    token: string | null,
    teamId: string,
    search: string,
    signal?: AbortSignal,
  ) =>
    apiRequest(
      token,
      `/directory/teams/${teamId}/eligible-technicians?search=${encodeURIComponent(search)}`,
      z.array(technicianSchema),
      {},
      signal,
    ),
  assignMember: (
    token: string | null,
    teamId: string,
    userId: string,
    memberRole: string,
    reason: string,
  ) =>
    apiRequest(
      token,
      `/directory/teams/${teamId}/members/${userId}`,
      memberSchema,
      {
        method: 'PUT',
        body: JSON.stringify({ member_role: memberRole, reason }),
      },
    ),
  removeMember: (
    token: string | null,
    teamId: string,
    userId: string,
    reason: string,
  ) =>
    apiRequest(
      token,
      `/directory/teams/${teamId}/members/${userId}`,
      z.undefined(),
      {
        method: 'DELETE',
        body: JSON.stringify({ reason }),
      },
    ),
  users: (token: string | null, query: string, signal?: AbortSignal) =>
    apiRequest(token, `/directory/users?${query}`, userPageSchema, {}, signal),
  createUser: (token: string | null, body: object) =>
    apiRequest(token, '/directory/users', directoryUserSchema, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  updateUser: (token: string | null, id: string, body: object) =>
    apiRequest(token, `/directory/users/${id}`, directoryUserSchema, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  updateUserStatus: (
    token: string | null,
    id: string,
    status: string,
    reason: string,
  ) =>
    apiRequest(token, `/directory/users/${id}/status`, directoryUserSchema, {
      method: 'PUT',
      body: JSON.stringify({ status, reason }),
    }),
}
