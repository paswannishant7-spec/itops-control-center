import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage } from '../../api/client'
import { useAuth } from '../auth/authContextValue'
import { directoryApi } from '../directory/directoryApi'
import { alertsApi } from './alertsApi'
import './alerts.css'

function displayDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

export function AlertsPage() {
  const { user, accessToken } = useAuth()
  const client = useQueryClient()
  const [state, setState] = useState('')
  const [actionReason, setActionReason] = useState<Record<string, string>>({})
  const canManage = user?.permissions.includes('alert:manage') ?? false
  const canAcknowledge =
    user?.permissions.includes('alert:acknowledge') ?? false
  const canResolve = user?.permissions.includes('alert:resolve') ?? false
  const query = new URLSearchParams({ offset: '0', limit: '100' })
  if (state) query.set('state', state)
  const alertQuery = useQuery({
    queryKey: ['alerts', query.toString()],
    queryFn: ({ signal }) =>
      alertsApi.alerts(accessToken, query.toString(), signal),
    retry: false,
  })
  const notifications = useQuery({
    queryKey: ['notifications'],
    queryFn: ({ signal }) => alertsApi.notifications(accessToken, signal),
    retry: false,
  })
  const preference = useQuery({
    queryKey: ['notification-preference'],
    queryFn: ({ signal }) => alertsApi.preference(accessToken, signal),
  })
  const policies = useQuery({
    queryKey: ['alert-policies'],
    queryFn: ({ signal }) => alertsApi.policies(accessToken, signal),
  })
  const rules = useQuery({
    queryKey: ['automation-rules'],
    queryFn: ({ signal }) => alertsApi.rules(accessToken, signal),
    enabled: canManage,
  })
  const teams = useQuery({
    queryKey: ['directory-teams', 'alert-automation'],
    queryFn: ({ signal }) => directoryApi.teams(accessToken, signal),
    enabled: canManage,
  })
  const transition = useMutation({
    mutationFn: ({ id, action }: { id: string; action: string }) =>
      alertsApi.transition(accessToken, id, action, actionReason[id] ?? ''),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['alerts'] }),
  })
  const markRead = useMutation({
    mutationFn: (id: string) => alertsApi.readNotification(accessToken, id),
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: ['notifications'] }),
  })
  const savePreference = useMutation({
    mutationFn: (body: object) => alertsApi.updatePreference(accessToken, body),
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: ['notification-preference'] }),
  })
  const createPolicy = useMutation({
    mutationFn: (body: object) => alertsApi.createPolicy(accessToken, body),
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: ['alert-policies'] }),
  })
  const createRule = useMutation({
    mutationFn: (body: object) => alertsApi.createRule(accessToken, body),
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: ['automation-rules'] }),
  })

  function formBody(
    event: FormEvent<HTMLFormElement>,
  ): Record<string, unknown> {
    event.preventDefault()
    return Object.fromEntries(new FormData(event.currentTarget))
  }

  const error =
    alertQuery.error ??
    notifications.error ??
    transition.error ??
    createPolicy.error ??
    createRule.error ??
    savePreference.error

  return (
    <main className="alerts-page">
      <header className="alerts-topbar">
        <Link className="brand" to="/">
          ← Workspace
        </Link>
        <div>
          <Link to="/monitoring">Monitoring</Link>
          <span>{user?.display_name}</span>
        </div>
      </header>
      <section className="alerts-heading">
        <div>
          <p className="eyebrow">Operations · Deterministic response</p>
          <h1>Alerts & automation</h1>
        </div>
        <div className="alert-summary">
          <strong>{alertQuery.data?.total ?? 0}</strong>
          <span>visible alerts</span>
          <strong>{notifications.data?.unread ?? 0}</strong>
          <span>unread</span>
        </div>
      </section>
      {error && (
        <p className="alerts-error" role="alert">
          {errorMessage(error)}
        </p>
      )}
      <div className="alerts-layout">
        <section className="alerts-panel alert-stream">
          <div className="panel-title">
            <div>
              <p className="eyebrow">Scoped conditions</p>
              <h2>Alert stream</h2>
            </div>
            <label>
              State
              <select
                value={state}
                onChange={(event) => setState(event.target.value)}
              >
                <option value="">All</option>
                {['TRIGGERED', 'ACKNOWLEDGED', 'SUPPRESSED', 'RESOLVED'].map(
                  (value) => (
                    <option key={value}>{value}</option>
                  ),
                )}
              </select>
            </label>
          </div>
          {alertQuery.isPending && <p>Loading alerts…</p>}
          {alertQuery.data?.total === 0 && <p>No alerts match this view.</p>}
          <ul>
            {alertQuery.data?.items.map((alert) => (
              <li key={alert.id}>
                <div className="alert-card-heading">
                  <span
                    className={`severity severity-${alert.severity.toLowerCase()}`}
                  >
                    {alert.severity}
                  </span>
                  <span className="alert-state">{alert.state}</span>
                </div>
                <h3>{alert.metric.replaceAll('_', ' ')}</h3>
                <p>
                  <strong>{alert.asset_tag}</strong> observed{' '}
                  {alert.observed_value} against {alert.threshold}
                </p>
                <small>
                  Last observed {displayDate(alert.last_observed_at)}
                </small>
                {alert.incident_ticket_id && (
                  <Link to={`/tickets/${alert.incident_ticket_id}`}>
                    {alert.incident_reference ?? 'Open incident'}
                  </Link>
                )}
                {alert.state !== 'RESOLVED' && (
                  <div className="alert-actions">
                    <input
                      aria-label={`Reason for ${alert.asset_tag}`}
                      placeholder="Action reason"
                      value={actionReason[alert.id] ?? ''}
                      onChange={(event) =>
                        setActionReason((current) => ({
                          ...current,
                          [alert.id]: event.target.value,
                        }))
                      }
                    />
                    {canAcknowledge && alert.state === 'TRIGGERED' && (
                      <button
                        disabled={(actionReason[alert.id]?.length ?? 0) < 3}
                        onClick={() =>
                          transition.mutate({
                            id: alert.id,
                            action: 'acknowledge',
                          })
                        }
                      >
                        Acknowledge
                      </button>
                    )}
                    {canResolve && (
                      <button
                        disabled={(actionReason[alert.id]?.length ?? 0) < 3}
                        onClick={() =>
                          transition.mutate({ id: alert.id, action: 'resolve' })
                        }
                      >
                        Resolve
                      </button>
                    )}
                    {canManage && (
                      <button
                        disabled={(actionReason[alert.id]?.length ?? 0) < 3}
                        onClick={() =>
                          transition.mutate({
                            id: alert.id,
                            action: 'suppress',
                          })
                        }
                      >
                        Suppress
                      </button>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
        <section className="alerts-panel notifications-panel">
          <div className="panel-title">
            <div>
              <p className="eyebrow">Personal inbox</p>
              <h2>Notifications</h2>
            </div>
            <span>{notifications.data?.unread ?? 0} unread</span>
          </div>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              const data = new FormData(event.currentTarget)
              savePreference.mutate({
                minimum_alert_severity: String(
                  data.get('minimum_alert_severity'),
                ),
                in_app_enabled: data.has('in_app_enabled'),
              })
            }}
          >
            <label>
              Minimum severity
              <select
                name="minimum_alert_severity"
                defaultValue={
                  preference.data?.minimum_alert_severity ?? 'WARNING'
                }
              >
                <option>INFO</option>
                <option>WARNING</option>
                <option>HIGH</option>
                <option>CRITICAL</option>
              </select>
            </label>
            <label className="check">
              <input
                name="in_app_enabled"
                type="checkbox"
                value="true"
                defaultChecked={preference.data?.in_app_enabled ?? true}
              />
              In-app alerts
            </label>
            <button>Save preferences</button>
          </form>
          <ul>
            {notifications.data?.items.map((item) => (
              <li key={item.id} className={item.read_at ? 'read' : ''}>
                <strong>{item.title}</strong>
                <span>{item.body}</span>
                <small>{displayDate(item.created_at)}</small>
                {!item.read_at && (
                  <button onClick={() => markRead.mutate(item.id)}>
                    Mark read
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      </div>
      {canManage && (
        <section className="automation-grid">
          <div className="alerts-panel">
            <p className="eyebrow">Configuration</p>
            <h2>Threshold policies</h2>
            <ul className="config-list">
              {policies.data?.items.map((item) => (
                <li key={item.id}>
                  <strong>{item.name}</strong>
                  <span>
                    {item.metric}{' '}
                    {item.operator.replaceAll('_', ' ').toLowerCase()}{' '}
                    {item.threshold} · {item.severity}
                  </span>
                </li>
              ))}
            </ul>
            <form onSubmit={(event) => createPolicy.mutate(formBody(event))}>
              <input
                name="name"
                aria-label="Policy name"
                placeholder="Policy name"
                required
                minLength={3}
              />
              <select name="metric" aria-label="Metric">
                <option>CPU_PERCENT</option>
                <option>MEMORY_PERCENT</option>
                <option>DISK_PERCENT</option>
                <option>DEVICE_OFFLINE</option>
                <option>HEARTBEAT_MISSED</option>
              </select>
              <select name="operator" aria-label="Operator">
                <option>GREATER_THAN</option>
                <option>AT_LEAST</option>
              </select>
              <input
                name="threshold"
                aria-label="Threshold"
                type="number"
                min="0"
                max="1000000"
                required
              />
              <select name="severity" aria-label="Severity">
                <option>WARNING</option>
                <option>HIGH</option>
                <option>CRITICAL</option>
              </select>
              <input
                name="reason"
                aria-label="Policy reason"
                placeholder="Change reason"
                required
                minLength={3}
              />
              <button>Create policy</button>
            </form>
          </div>
          <div className="alerts-panel">
            <p className="eyebrow">Deterministic actions</p>
            <h2>Automation rules</h2>
            <ul className="config-list">
              {rules.data?.items.map((item) => (
                <li key={item.id}>
                  <strong>{item.name}</strong>
                  <span>
                    {item.minimum_severity}+ ·{' '}
                    {item.create_incident ? 'incident' : ''}{' '}
                    {item.notify_team ? '+ notification' : ''}
                  </span>
                </li>
              ))}
            </ul>
            <form
              onSubmit={(event) => {
                const body = formBody(event)
                body.create_incident = true
                body.notify_team = true
                createRule.mutate(body)
              }}
            >
              <input
                name="name"
                aria-label="Rule name"
                placeholder="Rule name"
                required
                minLength={3}
              />
              <select name="minimum_severity" aria-label="Minimum severity">
                <option>WARNING</option>
                <option>HIGH</option>
                <option>CRITICAL</option>
              </select>
              <select
                name="assignment_team_id"
                aria-label="Assignment team"
                required
                defaultValue=""
              >
                <option value="">Select team</option>
                {teams.data?.map((team) => (
                  <option key={team.id} value={team.id}>
                    {team.name}
                  </option>
                ))}
              </select>
              <input
                name="reason"
                aria-label="Rule reason"
                placeholder="Change reason"
                required
                minLength={3}
              />
              <button>Create rule</button>
            </form>
          </div>
        </section>
      )}
    </main>
  )
}
