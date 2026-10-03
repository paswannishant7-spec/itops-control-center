import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { errorMessage } from '../../api/client'
import { useAuth } from '../auth/authContextValue'
import { directoryApi, type Department, type Location } from './directoryApi'

type Props =
  | {
      kind: 'department'
      records: Department[]
      canManage: boolean
      pending: boolean
      error: Error | null
      retry: () => void
    }
  | {
      kind: 'location'
      records: Location[]
      canManage: boolean
      pending: boolean
      error: Error | null
      retry: () => void
    }

export function ReferencePanel(props: Props) {
  const { user, accessToken } = useAuth()
  const queryClient = useQueryClient()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const editing = props.records.find((record) => record.id === editingId)
  const mutation = useMutation({
    mutationFn: async (body: Record<string, unknown>) => {
      if (props.kind === 'department')
        return editingId
          ? directoryApi.updateDepartment(accessToken, editingId, body)
          : directoryApi.createDepartment(accessToken, body)
      return editingId
        ? directoryApi.updateLocation(accessToken, editingId, body)
        : directoryApi.createLocation(accessToken, body)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: [`directory-${props.kind}s`, user?.id],
      })
      setNotice(
        `${props.kind === 'department' ? 'Department' : 'Location'} saved.`,
      )
      setEditingId(null)
    },
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setNotice('')
    const form = new FormData(event.currentTarget)
    const reason = String(form.get('reason') ?? '')
    if (props.kind === 'department') {
      mutation.mutate({
        ...(!editingId
          ? { code: String(form.get('code')), name: String(form.get('name')) }
          : { name: String(form.get('name')) }),
        description: String(form.get('description') ?? '') || null,
        ...(editingId ? { status: String(form.get('status')) } : {}),
        reason,
      })
      return
    }
    mutation.mutate({
      ...(!editingId
        ? { code: String(form.get('code')), name: String(form.get('name')) }
        : { name: String(form.get('name')) }),
      timezone: String(form.get('timezone')),
      address: String(form.get('address') ?? '') || null,
      ...(editingId ? { status: String(form.get('status')) } : {}),
      reason,
    })
  }

  const title = props.kind === 'department' ? 'Departments' : 'Locations'
  return (
    <section className="directory-panel" id={`${props.kind}s`}>
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Organization</p>
          <h2>{title}</h2>
        </div>
        <span>{props.records.length} configured</span>
      </div>
      {props.pending && <p role="status">Loading {title.toLowerCase()}…</p>}
      {props.error && (
        <p role="alert">
          {errorMessage(props.error)}{' '}
          <button type="button" onClick={props.retry}>
            Retry
          </button>
        </p>
      )}
      {!props.pending && !props.error && props.records.length === 0 && (
        <p className="empty-state">No {title.toLowerCase()} are configured.</p>
      )}
      {props.records.length > 0 && (
        <div className="table-wrap">
          <table>
            <caption className="sr-only">{title} directory</caption>
            <thead>
              <tr>
                <th scope="col">Code</th>
                <th scope="col">Name</th>
                <th scope="col">Status</th>
                <th scope="col">Usage</th>
                {props.canManage && <th scope="col">Action</th>}
              </tr>
            </thead>
            <tbody>
              {props.records.map((record) => (
                <tr key={record.id}>
                  <td>
                    <code>{record.code}</code>
                  </td>
                  <td>{record.name}</td>
                  <td>
                    <span
                      className={`status-pill ${record.status.toLowerCase()}`}
                    >
                      {record.status}
                    </span>
                  </td>
                  <td>
                    {record.user_count} users · {record.team_count} teams
                  </td>
                  {props.canManage && (
                    <td>
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => {
                          setEditingId(record.id)
                          setNotice('')
                          mutation.reset()
                        }}
                      >
                        Edit {record.name}
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {props.canManage && (
        <form
          className="management-form"
          key={editingId ?? 'new'}
          onSubmit={submit}
        >
          <h3>{editing ? `Edit ${editing.name}` : `Add ${props.kind}`}</h3>
          {!editing && (
            <label>
              Code
              <input name="code" required minLength={2} maxLength={32} />
            </label>
          )}
          <label>
            Name
            <input
              name="name"
              required
              minLength={2}
              maxLength={160}
              defaultValue={editing?.name}
            />
          </label>
          {props.kind === 'department' ? (
            <label>
              Description
              <textarea
                name="description"
                maxLength={500}
                defaultValue={
                  (editing as Department | undefined)?.description ?? ''
                }
              />
            </label>
          ) : (
            <>
              <label>
                IANA timezone
                <input
                  name="timezone"
                  required
                  defaultValue={
                    (editing as Location | undefined)?.timezone ?? 'UTC'
                  }
                />
              </label>
              <label>
                Address
                <textarea
                  name="address"
                  maxLength={500}
                  defaultValue={
                    (editing as Location | undefined)?.address ?? ''
                  }
                />
              </label>
            </>
          )}
          {editing && (
            <label>
              Status
              <select name="status" defaultValue={editing.status}>
                <option value="ACTIVE">Active</option>
                <option value="INACTIVE">Inactive</option>
              </select>
            </label>
          )}
          <label>
            Reason for change
            <textarea name="reason" required minLength={3} maxLength={500} />
          </label>
          <div className="form-actions">
            <button disabled={mutation.isPending}>
              {mutation.isPending ? 'Saving…' : 'Save'}
            </button>
            {editing && (
              <button
                type="button"
                className="secondary-button"
                onClick={() => setEditingId(null)}
              >
                Cancel
              </button>
            )}
          </div>
          {mutation.error && <p role="alert">{errorMessage(mutation.error)}</p>}
          {notice && <p role="status">{notice}</p>}
        </form>
      )}
    </section>
  )
}
