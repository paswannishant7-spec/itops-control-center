import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage } from '../../api/client'
import { useAuth } from '../auth/authContextValue'
import {
  directoryApi,
  type Department,
  type DirectoryUser,
  type Location,
} from './directoryApi'

const PAGE_SIZE = 10

export function UsersPanel({
  departments,
  locations,
}: {
  departments: Department[]
  locations: Location[]
}) {
  const { user, accessToken } = useAuth()
  const queryClient = useQueryClient()
  const [draftSearch, setDraftSearch] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [offset, setOffset] = useState(0)
  const [editing, setEditing] = useState<DirectoryUser | null>(null)
  const [notice, setNotice] = useState('')
  const canCreate = user?.permissions.includes('user:create') ?? false
  const canUpdate = user?.permissions.includes('user:update') ?? false
  const canDisable = user?.permissions.includes('user:disable') ?? false
  const query = useMemo(() => {
    const params = new URLSearchParams({
      offset: String(offset),
      limit: String(PAGE_SIZE),
    })
    if (search) params.set('search', search)
    if (status) params.set('status', status)
    return params.toString()
  }, [offset, search, status])
  const users = useQuery({
    queryKey: ['directory-users', user?.id, query],
    queryFn: ({ signal }) => directoryApi.users(accessToken, query, signal),
    retry: false,
  })
  const refresh = async () => {
    await queryClient.invalidateQueries({
      queryKey: ['directory-users', user?.id],
    })
  }
  const create = useMutation({
    mutationFn: (body: object) => directoryApi.createUser(accessToken, body),
    onSuccess: async (created) => {
      await refresh()
      setNotice(`${created.display_name} was created.`)
    },
  })
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: object }) =>
      directoryApi.updateUser(accessToken, id, body),
    onSuccess: async (updated) => {
      setEditing(updated)
      await refresh()
      setNotice(`${updated.display_name}'s profile was updated.`)
    },
  })
  const accountStatus = useMutation({
    mutationFn: ({
      id,
      status,
      reason,
    }: {
      id: string
      status: string
      reason: string
    }) => directoryApi.updateUserStatus(accessToken, id, status, reason),
    onSuccess: async (updated) => {
      setEditing(updated)
      await refresh()
      setNotice(
        `${updated.display_name} is now ${updated.status.toLowerCase()}.`,
      )
    },
  })

  function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setNotice('')
    const form = new FormData(event.currentTarget)
    create.mutate({
      email: String(form.get('email')),
      display_name: String(form.get('display_name')),
      initial_password: String(form.get('initial_password')),
      employee_number: String(form.get('employee_number') ?? '') || null,
      job_title: String(form.get('job_title') ?? '') || null,
      department_id: String(form.get('department_id') ?? '') || null,
      location_id: String(form.get('location_id') ?? '') || null,
      roles: [String(form.get('role'))],
      reason: String(form.get('reason')),
    })
  }

  function updateUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editing) return
    setNotice('')
    const form = new FormData(event.currentTarget)
    update.mutate({
      id: editing.id,
      body: {
        email: String(form.get('email')),
        display_name: String(form.get('display_name')),
        employee_number: String(form.get('employee_number') ?? '') || null,
        job_title: String(form.get('job_title') ?? '') || null,
        department_id: String(form.get('department_id') ?? '') || null,
        location_id: String(form.get('location_id') ?? '') || null,
        reason: String(form.get('reason')),
      },
    })
  }

  return (
    <section className="directory-panel directory-panel-wide" id="users">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Identity directory</p>
          <h2>Users</h2>
        </div>
        <span>{users.data?.total ?? 0} accounts</span>
      </div>
      <form
        className="filter-bar"
        role="search"
        onSubmit={(event) => {
          event.preventDefault()
          setOffset(0)
          setSearch(draftSearch.trim())
        }}
      >
        <label>
          Search users
          <input
            value={draftSearch}
            onChange={(event) => setDraftSearch(event.target.value)}
            placeholder="Name, email or employee number"
          />
        </label>
        <label>
          Account status
          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value)
              setOffset(0)
            }}
          >
            <option value="">All statuses</option>
            <option value="ACTIVE">Active</option>
            <option value="DISABLED">Disabled</option>
            <option value="LOCKED">Locked</option>
          </select>
        </label>
        <button>Apply filters</button>
      </form>
      {users.isPending && <p role="status">Loading users…</p>}
      {users.error && (
        <p role="alert">
          {errorMessage(users.error)}{' '}
          <button type="button" onClick={() => void users.refetch()}>
            Retry
          </button>
        </p>
      )}
      {users.data?.items.length === 0 && (
        <p className="empty-state">
          {search || status
            ? 'No users match these filters.'
            : 'No user accounts are configured.'}
        </p>
      )}
      {users.data && users.data.items.length > 0 && (
        <div className="table-wrap" aria-busy={users.isFetching}>
          <table>
            <caption className="sr-only">User directory</caption>
            <thead>
              <tr>
                <th scope="col">User</th>
                <th scope="col">Organization</th>
                <th scope="col">Roles</th>
                <th scope="col">Status</th>
                <th scope="col">Last login</th>
                {(canUpdate || canDisable) && <th scope="col">Action</th>}
              </tr>
            </thead>
            <tbody>
              {users.data.items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <strong>{item.display_name}</strong>
                    <small>{item.email}</small>
                    {item.employee_number && (
                      <small>{item.employee_number}</small>
                    )}
                  </td>
                  <td>
                    {item.department?.name ?? 'No department'}
                    <small>{item.location?.name ?? 'No location'}</small>
                  </td>
                  <td>{item.roles.join(', ') || 'No access role'}</td>
                  <td>
                    <span
                      className={`status-pill ${item.status.toLowerCase()}`}
                    >
                      {item.status}
                    </span>
                  </td>
                  <td>
                    {item.last_login_at
                      ? new Date(item.last_login_at).toLocaleString()
                      : 'Never'}
                  </td>
                  {(canUpdate || canDisable) && (
                    <td>
                      <button
                        className="text-button"
                        type="button"
                        onClick={() => {
                          setEditing(item)
                          setNotice('')
                        }}
                      >
                        Manage {item.display_name}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {users.data && users.data.total > PAGE_SIZE && (
        <nav className="pagination" aria-label="User pages">
          <button
            type="button"
            disabled={offset === 0 || users.isFetching}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </button>
          <span>
            {offset + 1}–{Math.min(offset + PAGE_SIZE, users.data.total)} of{' '}
            {users.data.total}
          </span>
          <button
            type="button"
            disabled={
              offset + PAGE_SIZE >= users.data.total || users.isFetching
            }
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </button>
        </nav>
      )}

      {canCreate && (
        <details className="management-details">
          <summary>Create user account</summary>
          <form className="management-form form-grid" onSubmit={createUser}>
            <label>
              Work email
              <input name="email" type="email" required />
            </label>
            <label>
              Display name
              <input
                name="display_name"
                required
                minLength={2}
                maxLength={160}
              />
            </label>
            <label>
              Initial password
              <input
                name="initial_password"
                type="password"
                required
                minLength={12}
                maxLength={128}
                autoComplete="new-password"
              />
            </label>
            <label>
              Employee number
              <input name="employee_number" maxLength={64} />
            </label>
            <label>
              Job title
              <input name="job_title" maxLength={120} />
            </label>
            <label>
              Initial role
              <select name="role" defaultValue="EMPLOYEE">
                <option value="EMPLOYEE">Employee</option>
                <option value="TECHNICIAN">Technician</option>
                <option value="IT_MANAGER">IT manager</option>
                <option value="ADMIN">Administrator</option>
              </select>
            </label>
            <OrganizationFields
              departments={departments}
              locations={locations}
            />
            <label className="full-field">
              Reason for creation
              <textarea name="reason" required minLength={3} maxLength={500} />
            </label>
            <button disabled={create.isPending}>
              {create.isPending ? 'Creating…' : 'Create user'}
            </button>
            {create.error && <p role="alert">{errorMessage(create.error)}</p>}
          </form>
        </details>
      )}

      {editing && (
        <section className="record-editor" aria-labelledby="user-editor-title">
          <div className="panel-heading">
            <h3 id="user-editor-title">Manage {editing.display_name}</h3>
            <button
              type="button"
              className="text-button"
              onClick={() => setEditing(null)}
            >
              Close
            </button>
          </div>
          {canUpdate && (
            <form
              className="management-form form-grid"
              key={editing.updated_at}
              onSubmit={updateUser}
            >
              <label>
                Work email
                <input
                  name="email"
                  type="email"
                  required
                  defaultValue={editing.email}
                />
              </label>
              <label>
                Display name
                <input
                  name="display_name"
                  required
                  defaultValue={editing.display_name}
                />
              </label>
              <label>
                Employee number
                <input
                  name="employee_number"
                  defaultValue={editing.employee_number ?? ''}
                />
              </label>
              <label>
                Job title
                <input
                  name="job_title"
                  defaultValue={editing.job_title ?? ''}
                />
              </label>
              <OrganizationFields
                departments={departments}
                locations={locations}
                departmentId={editing.department?.id}
                locationId={editing.location?.id}
              />
              <label className="full-field">
                Reason for profile change
                <textarea
                  name="reason"
                  required
                  minLength={3}
                  maxLength={500}
                />
              </label>
              <button disabled={update.isPending}>
                {update.isPending ? 'Saving…' : 'Save profile'}
              </button>
              {user?.permissions.includes('role:manage') && (
                <Link
                  className="secondary-link"
                  to={`/administration/access?userId=${editing.id}`}
                >
                  Manage access roles
                </Link>
              )}
              {update.error && <p role="alert">{errorMessage(update.error)}</p>}
            </form>
          )}
          {canDisable && (
            <form
              className="status-form"
              onSubmit={(event) => {
                event.preventDefault()
                const form = new FormData(event.currentTarget)
                accountStatus.mutate({
                  id: editing.id,
                  status: String(form.get('status')),
                  reason: String(form.get('reason')),
                })
              }}
            >
              <label>
                Account status
                <select name="status" defaultValue={editing.status}>
                  <option value="ACTIVE">Active</option>
                  <option value="DISABLED">Disabled</option>
                  <option value="LOCKED">Locked</option>
                </select>
              </label>
              <label>
                Reason for status change
                <input name="reason" required minLength={3} maxLength={500} />
              </label>
              <button
                disabled={accountStatus.isPending || editing.id === user?.id}
              >
                {accountStatus.isPending
                  ? 'Updating…'
                  : 'Update account status'}
              </button>
              {editing.id === user?.id && (
                <p>Your own status must be changed by another administrator.</p>
              )}
              {accountStatus.error && (
                <p role="alert">{errorMessage(accountStatus.error)}</p>
              )}
            </form>
          )}
        </section>
      )}
      {notice && <p role="status">{notice}</p>}
    </section>
  )
}

function OrganizationFields({
  departments,
  locations,
  departmentId = '',
  locationId = '',
}: {
  departments: Department[]
  locations: Location[]
  departmentId?: string
  locationId?: string
}) {
  return (
    <>
      <label>
        Department
        <select name="department_id" defaultValue={departmentId}>
          <option value="">No department</option>
          {departments
            .filter(
              (item) => item.status === 'ACTIVE' || item.id === departmentId,
            )
            .map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
        </select>
      </label>
      <label>
        Location
        <select name="location_id" defaultValue={locationId}>
          <option value="">No location</option>
          {locations
            .filter(
              (item) => item.status === 'ACTIVE' || item.id === locationId,
            )
            .map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
        </select>
      </label>
    </>
  )
}
