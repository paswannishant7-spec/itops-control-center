import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { errorMessage } from '../../api/client'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { useAuth } from '../auth/authContextValue'
import { assetApi } from './assetApi'
import './assets.css'

const assetTypes = [
  'LAPTOP',
  'DESKTOP',
  'MONITOR',
  'PRINTER',
  'SERVER',
  'NETWORK_DEVICE',
  'MOBILE_DEVICE',
]

export function AssetsPage() {
  const { user, accessToken } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [type, setType] = useState('')
  const [status, setStatus] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const debouncedSearch = useDebouncedValue(search.trim())
  const query = new URLSearchParams({ limit: '50', offset: '0' })
  if (debouncedSearch) query.set('search', debouncedSearch)
  if (type) query.set('asset_type', type)
  if (status) query.set('status', status)
  const assets = useQuery({
    queryKey: ['assets', query.toString()],
    queryFn: ({ signal }) =>
      assetApi.list(accessToken, query.toString(), signal),
    retry: false,
  })
  const create = useMutation({
    mutationFn: (body: object) => assetApi.create(accessToken, body),
    onSuccess: (asset) => {
      void queryClient.invalidateQueries({ queryKey: ['assets'] })
      void navigate(`/assets/${asset.id}`)
    },
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = Object.fromEntries(new FormData(event.currentTarget))
    create.mutate({
      ...data,
      serial_number: data.serial_number || null,
      hostname: data.hostname || null,
    })
  }

  return (
    <main className="assets-page">
      <header className="asset-topbar">
        <Link className="brand" to="/">
          ← Workspace
        </Link>
        <div>
          <Link to="/tickets">Tickets</Link>
          <span>{user?.display_name}</span>
        </div>
      </header>
      <section className="asset-heading">
        <div>
          <p className="eyebrow">Operations · Asset management</p>
          <h1>Asset inventory</h1>
          <p>
            Trace hardware identity, custody, health, warranty, and support
            relationships.
          </p>
        </div>
        {user?.permissions.includes('asset:create') && (
          <button
            type="button"
            onClick={() => setShowCreate((value) => !value)}
          >
            {showCreate ? 'Close form' : 'Register asset'}
          </button>
        )}
      </section>
      {showCreate && (
        <section className="asset-panel">
          <h2>Register hardware</h2>
          <form className="asset-form" onSubmit={submit}>
            <label>
              Asset tag
              <input name="asset_tag" required maxLength={64} />
            </label>
            <label>
              Type
              <select name="asset_type">
                {assetTypes.map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
            <label>
              Serial number
              <input name="serial_number" maxLength={128} />
            </label>
            <label>
              Hostname
              <input name="hostname" maxLength={255} />
            </label>
            <label className="wide-field">
              Reason
              <input name="reason" required minLength={3} maxLength={500} />
            </label>
            {create.error && (
              <p className="asset-error wide-field" role="alert">
                {errorMessage(create.error)}
              </p>
            )}
            <button type="submit" disabled={create.isPending}>
              {create.isPending ? 'Registering…' : 'Register asset'}
            </button>
          </form>
        </section>
      )}
      <section className="asset-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Visible to you</p>
            <h2>Hardware catalog</h2>
          </div>
          <span>{assets.data?.total ?? 0} assets</span>
        </div>
        <div className="asset-filters">
          <label>
            Search
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Tag, serial, hostname, model"
            />
          </label>
          <label>
            Type
            <select
              value={type}
              onChange={(event) => setType(event.target.value)}
            >
              <option value="">All types</option>
              {assetTypes.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label>
            Status
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">All statuses</option>
              {['ACTIVE', 'IN_REPAIR', 'LOST', 'RETIRED', 'DISPOSED'].map(
                (value) => (
                  <option key={value}>{value}</option>
                ),
              )}
            </select>
          </label>
        </div>
        {assets.isPending && <p className="asset-state">Loading assets…</p>}
        {assets.error && (
          <p className="asset-error" role="alert">
            {errorMessage(assets.error)}
          </p>
        )}
        {assets.data?.total === 0 && (
          <div className="asset-state">
            <p>
              {search || type || status
                ? 'No assets match these filters.'
                : 'No hardware has been registered yet.'}
            </p>
            {(search || type || status) && (
              <button
                type="button"
                onClick={() => {
                  setSearch('')
                  setType('')
                  setStatus('')
                }}
              >
                Clear filters
              </button>
            )}
          </div>
        )}
        {!!assets.data?.items.length && (
          <div className="asset-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Asset</th>
                  <th>Type</th>
                  <th>Owner</th>
                  <th>Department</th>
                  <th>Status</th>
                  <th>Health</th>
                </tr>
              </thead>
              <tbody>
                {assets.data.items.map((asset) => (
                  <tr key={asset.id}>
                    <td>
                      <Link to={`/assets/${asset.id}`}>
                        <strong>{asset.asset_tag}</strong>
                      </Link>
                      <span>
                        {asset.hostname ??
                          asset.serial_number ??
                          'No secondary identifier'}
                      </span>
                    </td>
                    <td>{asset.asset_type.replaceAll('_', ' ')}</td>
                    <td>{asset.owner?.display_name ?? 'Unassigned'}</td>
                    <td>{asset.department?.name ?? '—'}</td>
                    <td>
                      <span className="asset-badge">
                        {asset.status.replaceAll('_', ' ')}
                      </span>
                    </td>
                    <td>
                      <span
                        className={`health-${asset.health_status.toLowerCase()}`}
                      >
                        {asset.health_status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  )
}
