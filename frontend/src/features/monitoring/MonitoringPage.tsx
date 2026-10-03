import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage } from '../../api/client'
import { assetApi } from '../assets/assetApi'
import { useAuth } from '../auth/authContextValue'
import type { Enrollment } from './monitoringApi'
import { monitoringApi } from './monitoringApi'
import './monitoring.css'

function displayDate(value: string | null) {
  if (!value) return 'Never'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function bytes(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`
  return `${(value / 1024 ** 3).toFixed(1)} GB`
}

export function MonitoringPage() {
  const { user, accessToken } = useAuth()
  const queryClient = useQueryClient()
  const [status, setStatus] = useState('')
  const [selected, setSelected] = useState('')
  const [enrollment, setEnrollment] = useState<Enrollment | null>(null)
  const query = new URLSearchParams({ offset: '0', limit: '100' })
  if (status) query.set('status', status)
  const agents = useQuery({
    queryKey: ['monitoring-agents', query.toString()],
    queryFn: ({ signal }) =>
      monitoringApi.agents(accessToken, query.toString(), signal),
    retry: false,
  })
  const metrics = useQuery({
    queryKey: ['monitoring-metrics', selected],
    queryFn: ({ signal }) =>
      monitoringApi.metrics(accessToken, selected, signal),
    enabled: Boolean(selected),
    retry: false,
  })
  const canManage = user?.permissions.includes('monitoring:manage') ?? false
  const assets = useQuery({
    queryKey: ['assets', 'monitoring-enrollment'],
    queryFn: ({ signal }) =>
      assetApi.list(accessToken, 'status=ACTIVE&offset=0&limit=100', signal),
    enabled: canManage,
  })
  const createEnrollment = useMutation({
    mutationFn: (body: object) =>
      monitoringApi.createEnrollment(accessToken, body),
    onSuccess: (value) => {
      setEnrollment(value)
      void queryClient.invalidateQueries({ queryKey: ['monitoring-agents'] })
    },
  })
  const disable = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      monitoringApi.disable(accessToken, id, reason),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ['monitoring-agents'] }),
  })
  const selectedAgent = agents.data?.items.find(
    (value) => value.agent_id === selected,
  )
  const latest = metrics.data?.items[0]

  function submitEnrollment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setEnrollment(null)
    createEnrollment.mutate(
      Object.fromEntries(new FormData(event.currentTarget)),
    )
  }

  return (
    <main className="monitoring-page">
      <header className="monitoring-topbar">
        <Link className="brand" to="/">
          ← Workspace
        </Link>
        <div>
          <Link to="/assets">Assets</Link>
          <span>{user?.display_name}</span>
        </div>
      </header>
      <section className="monitoring-heading">
        <div>
          <p className="eyebrow">Operations · Endpoint visibility</p>
          <h1>Device monitoring</h1>
          <p>
            Inspect enrolled agents, heartbeat health, and bounded aggregate
            telemetry.
          </p>
        </div>
      </section>
      {canManage && (
        <section className="monitoring-panel enrollment-panel">
          <div>
            <p className="eyebrow">Administrator</p>
            <h2>Create one-time enrollment</h2>
          </div>
          <form onSubmit={submitEnrollment}>
            <label>
              Asset
              <select name="asset_id" required defaultValue="">
                <option value="">Select an active asset</option>
                {assets.data?.items.map((asset) => (
                  <option key={asset.id} value={asset.id}>
                    {asset.asset_tag} · {asset.hostname ?? asset.asset_type}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Reason
              <input name="reason" minLength={3} maxLength={500} required />
            </label>
            <button disabled={createEnrollment.isPending}>
              {createEnrollment.isPending ? 'Creating…' : 'Create token'}
            </button>
          </form>
          {enrollment && (
            <div className="enrollment-secret" role="status">
              <strong>Copy this token now</strong>
              <code>{enrollment.enrollment_token}</code>
              <span>
                Expires {displayDate(enrollment.expires_at)}. It is shown only
                once.
              </span>
            </div>
          )}
          {createEnrollment.error && (
            <p className="monitoring-error" role="alert">
              {errorMessage(createEnrollment.error)}
            </p>
          )}
        </section>
      )}
      <div className="monitoring-grid">
        <section className="monitoring-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Scoped fleet</p>
              <h2>Agents</h2>
            </div>
            <span>{agents.data?.total ?? 0}</span>
          </div>
          <label className="status-filter">
            Status
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">All statuses</option>
              {[
                'ONLINE',
                'OFFLINE',
                'DEGRADED',
                'UNREGISTERED',
                'DISABLED',
              ].map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          {agents.isPending && <p>Loading agents…</p>}
          {agents.error && (
            <p className="monitoring-error" role="alert">
              {errorMessage(agents.error)}
            </p>
          )}
          {agents.data?.total === 0 && <p>No agents match this view.</p>}
          <ul className="agent-list">
            {agents.data?.items.map((agent) => (
              <li
                key={agent.agent_id}
                className={selected === agent.agent_id ? 'selected' : ''}
              >
                <button
                  type="button"
                  onClick={() => setSelected(agent.agent_id)}
                >
                  <span>
                    <strong>{agent.asset_tag}</strong>
                    <small>{agent.hostname ?? 'Awaiting heartbeat'}</small>
                  </span>
                  <span
                    className={`agent-status status-${agent.status.toLowerCase()}`}
                  >
                    {agent.status}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
        <section className="monitoring-panel telemetry-panel">
          <div className="panel-heading">
            <h2>Latest telemetry</h2>
            <span>{metrics.data?.total ?? 0} samples</span>
          </div>
          {!selectedAgent && (
            <p>Select an agent to inspect its latest sample.</p>
          )}
          {selectedAgent && (
            <>
              <div className="agent-identity">
                <strong>{selectedAgent.asset_tag}</strong>
                <span>
                  {selectedAgent.agent_version
                    ? `Agent ${selectedAgent.agent_version}`
                    : 'Not enrolled'}
                </span>
                <small>
                  Last heartbeat {displayDate(selectedAgent.last_heartbeat)}
                </small>
                <small>
                  {selectedAgent.missed_heartbeat_count} missed heartbeats
                </small>
              </div>
              {latest ? (
                <div className="metric-grid">
                  {[
                    ['CPU', latest.cpu_percent],
                    ['Memory', latest.memory_percent],
                    ['Disk', latest.disk_percent],
                  ].map(([label, value]) => (
                    <div key={String(label)}>
                      <span>{label}</span>
                      <strong>{Number(value).toFixed(1)}%</strong>
                      <progress max={100} value={Number(value)} />
                    </div>
                  ))}
                  <div>
                    <span>Network sent</span>
                    <strong>{bytes(latest.network_bytes_sent)}</strong>
                  </div>
                  <div>
                    <span>Network received</span>
                    <strong>{bytes(latest.network_bytes_received)}</strong>
                  </div>
                  <small>Sampled {displayDate(latest.sampled_at)}</small>
                </div>
              ) : (
                <p>No retained metric samples.</p>
              )}
              {canManage && selectedAgent.status !== 'DISABLED' && (
                <form
                  className="disable-form"
                  onSubmit={(event) => {
                    event.preventDefault()
                    disable.mutate({
                      id: selectedAgent.agent_id,
                      reason: String(
                        new FormData(event.currentTarget).get('reason') ?? '',
                      ),
                    })
                  }}
                >
                  <label>
                    Disable reason
                    <input name="reason" minLength={3} required />
                  </label>
                  <button disabled={disable.isPending}>
                    Disable credential
                  </button>
                </form>
              )}
            </>
          )}
          {(metrics.error || disable.error) && (
            <p className="monitoring-error" role="alert">
              {errorMessage(metrics.error ?? disable.error)}
            </p>
          )}
        </section>
      </div>
    </main>
  )
}
