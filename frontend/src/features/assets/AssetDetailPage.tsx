import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { errorMessage } from '../../api/client'
import { useAuth } from '../auth/authContextValue'
import { directoryApi } from '../directory/directoryApi'
import { assetApi } from './assetApi'
import './assets.css'

function displayDate(value: string | null) {
  if (!value) return 'Not recorded'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

export function AssetDetailPage() {
  const { assetId = '' } = useParams()
  const { user, accessToken } = useAuth()
  const queryClient = useQueryClient()
  const asset = useQuery({
    queryKey: ['asset', assetId],
    queryFn: ({ signal }) => assetApi.detail(accessToken, assetId, signal),
    retry: false,
  })
  const history = useQuery({
    queryKey: ['asset-history', assetId],
    queryFn: ({ signal }) => assetApi.history(accessToken, assetId, signal),
    retry: false,
  })
  const tickets = useQuery({
    queryKey: ['asset-tickets', assetId],
    queryFn: ({ signal }) => assetApi.tickets(accessToken, assetId, signal),
    retry: false,
  })
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['asset', assetId] })
    void queryClient.invalidateQueries({ queryKey: ['asset-history', assetId] })
    void queryClient.invalidateQueries({ queryKey: ['assets'] })
  }
  const update = useMutation({
    mutationFn: (body: object) => assetApi.update(accessToken, assetId, body),
    onSuccess: refresh,
  })
  const assign = useMutation({
    mutationFn: (body: object) => assetApi.assign(accessToken, assetId, body),
    onSuccess: refresh,
  })
  const retire = useMutation({
    mutationFn: (reason: string) =>
      assetApi.retire(accessToken, assetId, reason),
    onSuccess: refresh,
  })
  const canUpdate = user?.permissions.includes('asset:update') ?? false
  const users = useQuery({
    queryKey: ['directory-users', 'asset-assignment'],
    queryFn: ({ signal }) =>
      directoryApi.users(
        accessToken,
        'status=ACTIVE&offset=0&limit=100',
        signal,
      ),
    enabled: canUpdate,
  })
  const departments = useQuery({
    queryKey: ['departments', 'asset-assignment'],
    queryFn: ({ signal }) => directoryApi.departments(accessToken, signal),
    enabled: canUpdate,
  })
  const locations = useQuery({
    queryKey: ['locations', 'asset-assignment'],
    queryFn: ({ signal }) => directoryApi.locations(accessToken, signal),
    enabled: canUpdate,
  })
  const current = asset.data

  function submitUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const values = Object.fromEntries(new FormData(event.currentTarget))
    update.mutate(values)
  }
  function submitAssignment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const values = Object.fromEntries(new FormData(event.currentTarget))
    assign.mutate({
      owner_id: values.owner_id || null,
      department_id: values.department_id || null,
      location_id: values.location_id || null,
      reason: values.reason,
    })
  }
  function submitRetirement(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    retire.mutate(String(new FormData(event.currentTarget).get('reason') ?? ''))
  }

  return (
    <main className="assets-page">
      <header className="asset-topbar">
        <Link className="brand" to="/assets">
          ← Asset inventory
        </Link>
        <span>{user?.display_name}</span>
      </header>
      {asset.isPending && <p className="asset-state">Loading asset…</p>}
      {asset.error && (
        <p className="asset-error" role="alert">
          {errorMessage(asset.error)}
        </p>
      )}
      {current && (
        <>
          <section className="asset-detail-heading">
            <div>
              <p className="eyebrow">
                {current.asset_type.replaceAll('_', ' ')}
              </p>
              <h1>{current.asset_tag}</h1>
              <p>
                {[current.manufacturer, current.model, current.hostname]
                  .filter(Boolean)
                  .join(' · ') || 'Inventory record'}
              </p>
            </div>
            <div>
              <span className="asset-badge">{current.status}</span>
              <span className={`health-${current.health_status.toLowerCase()}`}>
                {current.health_status}
              </span>
            </div>
          </section>
          <div className="asset-detail-grid">
            <div>
              <section className="asset-panel">
                <h2>Identity and network</h2>
                <dl className="asset-facts">
                  <div>
                    <dt>Serial number</dt>
                    <dd>{current.serial_number ?? '—'}</dd>
                  </div>
                  <div>
                    <dt>Hostname</dt>
                    <dd>{current.hostname ?? '—'}</dd>
                  </div>
                  <div>
                    <dt>Operating system</dt>
                    <dd>{current.operating_system ?? '—'}</dd>
                  </div>
                  <div>
                    <dt>IP address</dt>
                    <dd>{current.ip_address ?? '—'}</dd>
                  </div>
                  <div>
                    <dt>MAC address</dt>
                    <dd>{current.mac_address ?? '—'}</dd>
                  </div>
                  <div>
                    <dt>Last seen</dt>
                    <dd>{displayDate(current.last_seen)}</dd>
                  </div>
                </dl>
              </section>
              <section className="asset-panel">
                <div className="panel-heading">
                  <h2>Related tickets</h2>
                  <span>{tickets.data?.length ?? 0}</span>
                </div>
                {tickets.data?.length === 0 && (
                  <p className="asset-state">No visible tickets are linked.</p>
                )}
                <ul className="asset-list">
                  {tickets.data?.map((ticket) => (
                    <li key={ticket.id}>
                      <Link to={`/tickets/${ticket.id}`}>
                        {ticket.reference} · {ticket.title}
                      </Link>
                      <span>
                        {ticket.status} · {ticket.priority}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
              <section className="asset-panel">
                <h2>Custody history</h2>
                <ol className="asset-timeline">
                  {history.data?.assignments.map((item) => (
                    <li key={item.id}>
                      <strong>
                        {item.owner?.display_name ??
                          item.department?.name ??
                          item.location?.name ??
                          'Unassigned'}
                      </strong>
                      <span>{item.reason}</span>
                      <small>
                        {displayDate(item.started_at)} →{' '}
                        {displayDate(item.ended_at)}
                      </small>
                    </li>
                  ))}
                </ol>
              </section>
              <section className="asset-panel">
                <h2>Audit trail</h2>
                <ol className="asset-timeline">
                  {history.data?.events.map((item) => (
                    <li key={item.id}>
                      <strong>{item.action.replaceAll('.', ' ')}</strong>
                      <span>{item.reason}</span>
                      <small>
                        {item.actor.display_name} ·{' '}
                        {displayDate(item.created_at)}
                      </small>
                    </li>
                  ))}
                </ol>
              </section>
            </div>
            <aside>
              <section className="asset-panel">
                <h2>Ownership</h2>
                <dl className="asset-facts">
                  <div>
                    <dt>Owner</dt>
                    <dd>{current.owner?.display_name ?? 'Unassigned'}</dd>
                  </div>
                  <div>
                    <dt>Department</dt>
                    <dd>{current.department?.name ?? '—'}</dd>
                  </div>
                  <div>
                    <dt>Location</dt>
                    <dd>{current.location?.name ?? '—'}</dd>
                  </div>
                  <div>
                    <dt>Purchased</dt>
                    <dd>{current.purchase_date ?? '—'}</dd>
                  </div>
                  <div>
                    <dt>Warranty ends</dt>
                    <dd>{current.warranty_end ?? '—'}</dd>
                  </div>
                </dl>
              </section>
              {canUpdate &&
                !['RETIRED', 'DISPOSED'].includes(current.status) && (
                  <>
                    <section className="asset-panel">
                      <h2>Update inventory</h2>
                      <form className="asset-side-form" onSubmit={submitUpdate}>
                        <label>
                          Hostname
                          <input
                            name="hostname"
                            defaultValue={current.hostname ?? ''}
                          />
                        </label>
                        <label>
                          Health
                          <select
                            name="health_status"
                            defaultValue={current.health_status}
                          >
                            {[
                              'UNKNOWN',
                              'HEALTHY',
                              'WARNING',
                              'CRITICAL',
                              'OFFLINE',
                            ].map((value) => (
                              <option key={value}>{value}</option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Reason
                          <input name="reason" minLength={3} required />
                        </label>
                        <button disabled={update.isPending}>
                          Save changes
                        </button>
                      </form>
                    </section>
                    <section className="asset-panel">
                      <h2>Transfer custody</h2>
                      <form
                        className="asset-side-form"
                        onSubmit={submitAssignment}
                      >
                        <label>
                          Owner
                          <select
                            name="owner_id"
                            defaultValue={current.owner?.id ?? ''}
                          >
                            <option value="">No individual owner</option>
                            {users.data?.items.map((value) => (
                              <option key={value.id} value={value.id}>
                                {value.display_name}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Department
                          <select
                            name="department_id"
                            defaultValue={current.department?.id ?? ''}
                          >
                            <option value="">No department</option>
                            {departments.data
                              ?.filter((value) => value.status === 'ACTIVE')
                              .map((value) => (
                                <option key={value.id} value={value.id}>
                                  {value.name}
                                </option>
                              ))}
                          </select>
                        </label>
                        <label>
                          Location
                          <select
                            name="location_id"
                            defaultValue={current.location?.id ?? ''}
                          >
                            <option value="">No location</option>
                            {locations.data
                              ?.filter((value) => value.status === 'ACTIVE')
                              .map((value) => (
                                <option key={value.id} value={value.id}>
                                  {value.name}
                                </option>
                              ))}
                          </select>
                        </label>
                        <label>
                          Reason
                          <input name="reason" minLength={3} required />
                        </label>
                        <button disabled={assign.isPending}>
                          Record assignment
                        </button>
                      </form>
                    </section>
                  </>
                )}
              {user?.permissions.includes('asset:retire') &&
                current.status !== 'RETIRED' && (
                  <section className="asset-panel danger-panel">
                    <h2>Retire asset</h2>
                    <form
                      className="asset-side-form"
                      onSubmit={submitRetirement}
                    >
                      <label>
                        Reason
                        <input name="reason" minLength={3} required />
                      </label>
                      <button disabled={retire.isPending}>Retire asset</button>
                    </form>
                  </section>
                )}
              {(update.error || assign.error || retire.error) && (
                <p className="asset-error" role="alert">
                  {errorMessage(update.error ?? assign.error ?? retire.error)}
                </p>
              )}
            </aside>
          </div>
        </>
      )}
    </main>
  )
}
