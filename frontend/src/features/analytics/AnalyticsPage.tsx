import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage } from '../../api/client'
import { useAuth } from '../auth/authContextValue'
import { analyticsApi } from './analyticsApi'
import type { Dashboard, VolumePoint } from './analyticsApi'
import './analytics.css'

const windows = [7, 30, 90] as const

function metric(value: number | null, suffix = '') {
  return value === null ? '—' : `${value.toLocaleString()}${suffix}`
}

function dateTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function VolumeChart({
  points,
  granularity,
}: {
  points: VolumePoint[]
  granularity: string
}) {
  const width = 720
  const height = 220
  const padding = 24
  const maximum = Math.max(
    1,
    ...points.flatMap((point) => [point.created, point.resolved]),
  )
  const x = (index: number) =>
    padding + (index * (width - padding * 2)) / Math.max(1, points.length - 1)
  const y = (value: number) =>
    height - padding - (value * (height - padding * 2)) / maximum
  const line = (field: 'created' | 'resolved') =>
    points.map((point, index) => `${x(index)},${y(point[field])}`).join(' ')

  return (
    <div className="volume-chart">
      <svg
        role="img"
        aria-label={`${granularity} created and resolved ticket volume`}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
      >
        <line
          x1={padding}
          y1={height - padding}
          x2={width - padding}
          y2={height - padding}
        />
        <polyline className="created-line" points={line('created')} />
        <polyline className="resolved-line" points={line('resolved')} />
      </svg>
      <div className="chart-legend" aria-hidden="true">
        <span>
          <i className="created-key" />
          Created
        </span>
        <span>
          <i className="resolved-key" />
          Resolved
        </span>
        <span>Peak {maximum}</span>
      </div>
    </div>
  )
}

function BarList({
  items,
}: {
  items: Array<{ label: string; count: number }>
}) {
  const maximum = Math.max(1, ...items.map((item) => item.count))
  if (!items.length)
    return <p className="analytics-empty">No activity in this window.</p>
  return (
    <ol className="bar-list">
      {items.map((item) => (
        <li key={item.label}>
          <div>
            <span>{item.label}</span>
            <strong>{item.count}</strong>
          </div>
          <span className="bar-track">
            <i style={{ width: `${(item.count / maximum) * 100}%` }} />
          </span>
        </li>
      ))}
    </ol>
  )
}

function Performance({ data }: { data: Dashboard['performance'] }) {
  const values = [
    [
      'MTTR',
      metric(data.mttr.minutes, 'm'),
      data.mttr.sample_size,
      'Mean time to resolution',
    ],
    [
      'MTTA',
      metric(data.mtta.minutes, 'm'),
      data.mtta.sample_size,
      'Mean time to first response',
    ],
    [
      'SLA compliance',
      metric(data.sla_compliance.percent, '%'),
      data.sla_compliance.sample_size,
      'Resolved within target',
    ],
    [
      'Reopen rate',
      metric(data.reopen_rate.percent, '%'),
      data.reopen_rate.sample_size,
      'Resolved tickets reopened',
    ],
    [
      'First-contact proxy',
      metric(data.first_contact_resolution_proxy.percent, '%'),
      data.first_contact_resolution_proxy.sample_size,
      'Resolved without a recorded reopen',
    ],
  ] as const
  return (
    <section className="performance-grid" aria-label="Performance metrics">
      {values.map(([label, value, samples, description]) => (
        <article key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
          <small>{description}</small>
          <em>
            {samples} sample{samples === 1 ? '' : 's'}
          </em>
        </article>
      ))}
    </section>
  )
}

export function AnalyticsPage() {
  const { user, accessToken } = useAuth()
  const [days, setDays] = useState<number>(30)
  const [granularity, setGranularity] = useState<
    'daily' | 'weekly' | 'monthly'
  >('daily')
  const dashboard = useQuery({
    queryKey: ['analytics-dashboard', days],
    queryFn: ({ signal }) => analyticsApi.dashboard(accessToken, days, signal),
    retry: false,
  })
  const data = dashboard.data

  return (
    <main className="analytics-page">
      <header className="analytics-topbar">
        <Link className="brand" to="/">
          ← Workspace
        </Link>
        <nav aria-label="Operations links">
          <Link to="/tickets">Tickets</Link>
          <Link to="/alerts">Alerts</Link>
          <Link to="/monitoring">Monitoring</Link>
          <span>{user?.display_name}</span>
        </nav>
      </header>
      <section className="command-heading">
        <div>
          <p className="eyebrow">Operations intelligence · Live scope</p>
          <h1>
            {data?.scope.audience === 'TEAM'
              ? 'Technician operations'
              : 'IT command center'}
          </h1>
          <p>
            See what is broken, what is urgent, and whether service performance
            is moving in the right direction.
          </p>
        </div>
        <div className="window-control" aria-label="Analytics window">
          <span>Reporting window</span>
          <div>
            {windows.map((value) => (
              <button
                key={value}
                type="button"
                className={days === value ? 'active' : ''}
                aria-pressed={days === value}
                onClick={() => setDays(value)}
              >
                {value}d
              </button>
            ))}
          </div>
        </div>
      </section>

      {dashboard.isPending && (
        <div className="analytics-state">Assembling operational picture…</div>
      )}
      {dashboard.error && (
        <div className="analytics-state error" role="alert">
          {errorMessage(dashboard.error)}
        </div>
      )}
      {data && (
        <>
          <div className="scope-line">
            <span className="live-pulse" />
            {data.scope.label}
            <small>Updated {dateTime(data.generated_at)}</small>
          </div>
          <section
            className="signal-grid"
            aria-label="Current operational signals"
          >
            {[
              ['Open tickets', data.summary.open_tickets, 'neutral'],
              ['Assigned to me', data.summary.assigned_to_me, 'neutral'],
              ['Unassigned', data.summary.unassigned_tickets, 'warning'],
              ['Active incidents', data.summary.active_incidents, 'neutral'],
              [
                'Critical incidents',
                data.summary.critical_incidents,
                'critical',
              ],
              ['SLA at risk', data.summary.sla_at_risk, 'warning'],
              ['SLA breached', data.summary.sla_breached, 'critical'],
              ['Online devices', data.summary.online_devices, 'healthy'],
              ['Offline devices', data.summary.offline_devices, 'warning'],
              ['Critical alerts', data.summary.critical_alerts, 'critical'],
            ].map(([label, value, tone]) => (
              <article key={String(label)} className={`signal-card ${tone}`}>
                <span>{label}</span>
                <strong>{value}</strong>
              </article>
            ))}
          </section>

          <Performance data={data.performance} />

          <section className="analytics-panel volume-panel">
            <div className="panel-title">
              <div>
                <p className="eyebrow">Flow</p>
                <h2>Ticket volume</h2>
              </div>
              <div
                className="granularity-control"
                aria-label="Ticket volume granularity"
              >
                {(['daily', 'weekly', 'monthly'] as const).map((value) => (
                  <button
                    type="button"
                    key={value}
                    className={granularity === value ? 'active' : ''}
                    aria-pressed={granularity === value}
                    onClick={() => setGranularity(value)}
                  >
                    {value}
                  </button>
                ))}
              </div>
            </div>
            <VolumeChart
              points={data.ticket_volume[granularity]}
              granularity={granularity}
            />
          </section>

          <div className="analytics-columns">
            <section className="analytics-panel attention-panel">
              <div className="panel-title">
                <div>
                  <p className="eyebrow">Act now</p>
                  <h2>Urgent queue</h2>
                </div>
                <span>{data.summary.unassigned_tickets} unassigned</span>
              </div>
              {data.attention.urgent_tickets.length === 0 && (
                <p className="analytics-empty">
                  No active tickets in your scope.
                </p>
              )}
              <ul className="urgent-list">
                {data.attention.urgent_tickets.map((ticket) => (
                  <li key={ticket.id}>
                    <Link to={`/tickets/${ticket.id}`}>
                      <span>
                        <strong>{ticket.reference}</strong>
                        {ticket.title}
                      </span>
                      <span>
                        <b
                          className={`priority-${ticket.priority.toLowerCase()}`}
                        >
                          {ticket.priority}
                        </b>
                        <small>{ticket.sla_state ?? ticket.status}</small>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
            <section className="analytics-panel">
              <div className="panel-title">
                <div>
                  <p className="eyebrow">Capacity</p>
                  <h2>Technician workload</h2>
                </div>
                <span>Open / resolved</span>
              </div>
              {data.technician_workload.length === 0 && (
                <p className="analytics-empty">
                  No assigned activity in this window.
                </p>
              )}
              <ul className="workload-list">
                {data.technician_workload.map((item) => {
                  const total = Math.max(
                    1,
                    item.assigned_open + item.resolved_in_window,
                  )
                  return (
                    <li key={item.technician_id}>
                      <div>
                        <strong>{item.technician_name}</strong>
                        <span>
                          {item.assigned_open} open · {item.resolved_in_window}{' '}
                          resolved
                        </span>
                      </div>
                      <span>
                        <i
                          style={{
                            width: `${(item.assigned_open / total) * 100}%`,
                          }}
                        />
                      </span>
                    </li>
                  )
                })}
              </ul>
            </section>
          </div>

          <div className="analytics-columns three">
            <section className="analytics-panel">
              <div className="panel-title">
                <div>
                  <p className="eyebrow">Demand</p>
                  <h2>Top categories</h2>
                </div>
              </div>
              <BarList items={data.by_category} />
            </section>
            <section className="analytics-panel">
              <div className="panel-title">
                <div>
                  <p className="eyebrow">Patterns</p>
                  <h2>Recurring issues</h2>
                </div>
              </div>
              {data.recurring_issues.length === 0 ? (
                <p className="analytics-empty">
                  No repeated category patterns yet.
                </p>
              ) : (
                <ol className="rank-list">
                  {data.recurring_issues.map((item) => (
                    <li key={`${item.category}-${item.subcategory}`}>
                      <span>
                        <strong>{item.subcategory ?? item.category}</strong>
                        <small>
                          {item.subcategory ? item.category : 'Category'}
                        </small>
                      </span>
                      <b>{item.ticket_count}</b>
                    </li>
                  ))}
                </ol>
              )}
            </section>
            <section className="analytics-panel">
              <div className="panel-title">
                <div>
                  <p className="eyebrow">Fleet</p>
                  <h2>Device health</h2>
                </div>
                <span>{data.summary.unhealthy_devices} unhealthy</span>
              </div>
              {data.attention.device_health_issues.length === 0 ? (
                <p className="analytics-empty">
                  No unhealthy devices in scope.
                </p>
              ) : (
                <ul className="rank-list">
                  {data.attention.device_health_issues.map((device) => (
                    <li key={device.agent_id}>
                      <Link to={`/assets/${device.asset_id}`}>
                        <span>
                          <strong>{device.asset_tag}</strong>
                          <small>
                            {device.hostname ?? device.health_status}
                          </small>
                        </span>
                        <b className="health-badge">{device.status}</b>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          <div className="analytics-columns three">
            <section className="analytics-panel">
              <div className="panel-title">
                <div>
                  <p className="eyebrow">Urgency</p>
                  <h2>Demand by priority</h2>
                </div>
              </div>
              <BarList items={data.by_priority} />
            </section>
            <section className="analytics-panel">
              <div className="panel-title">
                <div>
                  <p className="eyebrow">Business impact</p>
                  <h2>Demand by department</h2>
                </div>
              </div>
              <BarList items={data.by_department} />
            </section>
            <section className="analytics-panel">
              <div className="panel-title">
                <div>
                  <p className="eyebrow">Reliability</p>
                  <h2>Incident-heavy assets</h2>
                </div>
              </div>
              {data.asset_incident_frequency.length === 0 ? (
                <p className="analytics-empty">
                  No asset-linked incidents in this window.
                </p>
              ) : (
                <ol className="rank-list">
                  {data.asset_incident_frequency.map((item) => (
                    <li key={item.asset_id}>
                      <Link to={`/assets/${item.asset_id}`}>
                        <span>
                          <strong>{item.asset_tag}</strong>
                          <small>Linked incidents</small>
                        </span>
                        <b>{item.incident_count}</b>
                      </Link>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </div>

          <div className="analytics-columns">
            <section className="analytics-panel">
              <div className="panel-title">
                <div>
                  <p className="eyebrow">Risk</p>
                  <h2>Critical alerts</h2>
                </div>
                <Link to="/alerts">Open alert stream →</Link>
              </div>
              {data.attention.critical_alerts.length === 0 ? (
                <p className="analytics-empty">No active critical alerts.</p>
              ) : (
                <ul className="rank-list">
                  {data.attention.critical_alerts.map((alert) => (
                    <li key={alert.id}>
                      <span>
                        <strong>{alert.asset_tag}</strong>
                        <small>
                          {alert.metric.replaceAll('_', ' ')} ·{' '}
                          {dateTime(alert.triggered_at)}
                        </small>
                      </span>
                      <b className="critical-badge">{alert.state}</b>
                    </li>
                  ))}
                </ul>
              )}
            </section>
            <section className="analytics-panel ai-panel">
              <div className="panel-title">
                <div>
                  <p className="eyebrow">Human review</p>
                  <h2>AI assistance outcomes</h2>
                </div>
                <span>
                  {data.ai_assistance.reviewed_recommendations} reviewed
                </span>
              </div>
              <div className="ai-outcomes">
                <div>
                  <strong>
                    {metric(data.ai_assistance.acceptance_rate, '%')}
                  </strong>
                  <span>Accepted</span>
                </div>
                <div>
                  <strong>{metric(data.ai_assistance.edit_rate, '%')}</strong>
                  <span>Edited</span>
                </div>
                <div>
                  <strong>
                    {metric(data.ai_assistance.rejection_rate, '%')}
                  </strong>
                  <span>Rejected</span>
                </div>
              </div>
              <p>{data.ai_assistance.label}</p>
            </section>
          </div>
        </>
      )}
    </main>
  )
}
