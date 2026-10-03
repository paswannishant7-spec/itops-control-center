import { useState, type FormEvent } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { z } from 'zod'
import { apiBase } from '../auth/authApi'
import { useAuth } from '../auth/authContextValue'
import './access.css'

const rolesSchema = z.array(
  z.object({ code: z.string(), permissions: z.array(z.string()) }),
)
const grantsSchema = z.object({
  roles: z.array(z.string()),
  permissions: z.array(z.string()),
})

export function AccessPage() {
  const { user, accessToken } = useAuth()
  const [searchParams] = useSearchParams()
  const [target, setTarget] = useState(searchParams.get('userId') ?? '')
  const [selected, setSelected] = useState<string[]>([])
  const [reason, setReason] = useState('')
  const [notice, setNotice] = useState('')
  const canManage = user?.permissions.includes('role:manage') ?? false
  async function request(path: string, init?: RequestInit): Promise<unknown> {
    const response = await fetch(`${apiBase}/access${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
    })
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as {
        title?: string
      }
      throw new Error(body.title ?? 'Unable to complete this request')
    }
    return response.json()
  }
  const roles = useQuery({
    queryKey: ['access-roles', user?.id],
    queryFn: async () => rolesSchema.parse(await request('/roles')),
    retry: false,
  })
  const lookup = useMutation({
    mutationFn: async (id: string) =>
      grantsSchema.parse(await request(`/users/${id}/roles`)),
    onSuccess: (result) => {
      setSelected(result.roles)
      setNotice('')
    },
  })
  const save = useMutation({
    mutationFn: async () => {
      await request(`/users/${target}/roles`, {
        method: 'PUT',
        body: JSON.stringify({ roles: selected, reason }),
      })
    },
    onSuccess: () => {
      setNotice(
        'Role assignments saved. The change is recorded in the audit history.',
      )
      setReason('')
      lookup.reset()
    },
  })
  function findUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setNotice('')
    save.reset()
    if (!z.string().uuid().safeParse(target).success) {
      setNotice('Enter a valid user ID.')
      return
    }
    lookup.mutate(target)
  }
  return (
    <main className="access-page">
      <header className="topbar">
        <Link className="brand" to="/">
          ← Workspace
        </Link>
        <span>{user?.display_name}</span>
      </header>
      <div className="access-heading">
        <p className="eyebrow">Administration</p>
        <h1>Access management</h1>
        <p>
          Review system roles and control who can use each part of the platform.
        </p>
      </div>
      {roles.isPending && <p role="status">Loading roles…</p>}
      {roles.error && (
        <p role="alert">
          {roles.error.message}{' '}
          <button onClick={() => void roles.refetch()}>Retry</button>
        </p>
      )}
      {roles.data?.length === 0 && (
        <p>No roles are configured. Run the database migrations.</p>
      )}
      <section className="role-grid" aria-label="System roles">
        {roles.data?.map((role) => (
          <article key={role.code}>
            <h2>{role.code.replaceAll('_', ' ')}</h2>
            <p>{role.permissions.length} permissions</p>
            <details>
              <summary>View permissions</summary>
              <ul>
                {role.permissions.map((p) => (
                  <li key={p}>
                    <code>{p}</code>
                  </li>
                ))}
              </ul>
            </details>
          </article>
        ))}
      </section>
      {canManage && (
        <section
          className="assignment-panel"
          aria-labelledby="assignment-title"
        >
          <h2 id="assignment-title">Assign user roles</h2>
          <p>
            Use an existing user's ID. Your own roles must be changed by another
            administrator.
          </p>
          <form onSubmit={findUser}>
            <label htmlFor="target-user">User ID</label>
            <input
              id="target-user"
              value={target}
              onChange={(e) => {
                setTarget(e.target.value.trim())
                lookup.reset()
                save.reset()
                setNotice('')
              }}
              required
              disabled={lookup.isPending || save.isPending}
            />
            <button disabled={lookup.isPending || save.isPending}>
              Load assignments
            </button>
          </form>
          {lookup.error && <p role="alert">{lookup.error.message}</p>}
          {lookup.isSuccess && (
            <form
              onSubmit={(e) => {
                e.preventDefault()
                save.mutate()
              }}
            >
              <fieldset disabled={save.isPending}>
                <legend>Roles</legend>
                {roles.data?.map((role) => (
                  <label key={role.code}>
                    <input
                      type="checkbox"
                      checked={selected.includes(role.code)}
                      onChange={(e) =>
                        setSelected((old) =>
                          e.target.checked
                            ? [...old, role.code]
                            : old.filter((r) => r !== role.code),
                        )
                      }
                    />
                    {role.code.replaceAll('_', ' ')}
                  </label>
                ))}
              </fieldset>
              <label htmlFor="assignment-reason">Reason for change</label>
              <textarea
                id="assignment-reason"
                required
                minLength={3}
                maxLength={500}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <button disabled={save.isPending || target === user?.id}>
                {save.isPending ? 'Saving…' : 'Save roles'}
              </button>
            </form>
          )}
          {save.error && <p role="alert">{save.error.message}</p>}
          {notice && <p role="status">{notice}</p>}
        </section>
      )}
    </main>
  )
}
