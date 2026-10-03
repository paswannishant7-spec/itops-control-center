import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { analyticsApi } from '../analytics/analyticsApi'
import { useAuth } from '../auth/authContextValue'
import { ticketApi, type TicketSummary } from '../tickets/ticketApi'

type Metric = {
  label: string
  value: string | number
  detail: string
  tone?: 'critical' | 'warning' | 'positive'
}

function roleName(roles: string[] | undefined) {
  if (roles?.includes('ADMIN')) return 'ADMIN'
  if (roles?.includes('IT_MANAGER')) return 'IT_MANAGER'
  if (roles?.includes('TECHNICIAN')) return 'TECHNICIAN'
  return 'EMPLOYEE'
}

function isOpen(ticket: TicketSummary) {
  return !['RESOLVED', 'CLOSED', 'CANCELLED'].includes(ticket.status)
}

export function FoundationPage() {
  const { user, accessToken } = useAuth()
  const role = roleName(user?.roles)
  const canViewTickets =
    user?.permissions.some((permission) =>
      permission.startsWith('ticket:view_'),
    ) ?? false
  const canViewAnalytics = user?.permissions.includes('analytics:view') ?? false
  const tickets = useQuery({
    queryKey: ['dashboard-tickets', user?.id],
    queryFn: ({ signal }) =>
      ticketApi.list(accessToken, 'offset=0&limit=25', signal),
    enabled: canViewTickets,
    retry: false,
  })
  const analytics = useQuery({
    queryKey: ['dashboard-summary', user?.id],
    queryFn: ({ signal }) => analyticsApi.dashboard(accessToken, 30, signal),
    enabled: canViewAnalytics,
    retry: false,
  })

  const visibleTickets = tickets.data?.items ?? []
  const openTickets = visibleTickets.filter(isOpen)
  const assignedToMe = openTickets.filter(
    (ticket) => ticket.assigned_technician?.id === user?.id,
  )
  const urgent = openTickets.filter((ticket) =>
    ['CRITICAL', 'HIGH'].includes(ticket.priority),
  )
  const atRisk = openTickets.filter((ticket) =>
    ['AT_RISK', 'BREACHED'].includes(ticket.sla_state ?? ''),
  )
  const unassigned = openTickets.filter(
    (ticket) => !ticket.assigned_technician && !ticket.assignment_team,
  )

  const titles = {
    EMPLOYEE: [
      'My support',
      'Track requests and respond to anything waiting on you.',
    ],
    TECHNICIAN: [
      'Service desk overview',
      'Prioritize urgent work, SLA risk, and the queue requiring ownership.',
    ],
    IT_MANAGER: [
      'Operations overview',
      'Monitor workload, service performance, and operational risk.',
    ],
    ADMIN: [
      'System overview',
      'Review platform health, access, assets, and recent operational activity.',
    ],
  } as const

  const metrics: Metric[] =
    role === 'EMPLOYEE'
      ? [
          {
            label: 'My open tickets',
            value: openTickets.length,
            detail: 'Active requests',
          },
          {
            label: 'Pending action',
            value: openTickets.filter(
              (ticket) => ticket.status === 'PENDING_USER',
            ).length,
            detail: 'Waiting for your response',
            tone: 'warning',
          },
          {
            label: 'Recent activity',
            value: visibleTickets.length,
            detail: 'Visible requests',
          },
          {
            label: 'SLA attention',
            value: atRisk.length,
            detail: 'At risk or breached',
            tone: atRisk.length ? 'critical' : 'positive',
          },
        ]
      : role === 'TECHNICIAN'
        ? [
            {
              label: 'Assigned to me',
              value: assignedToMe.length,
              detail: 'Open tickets',
            },
            {
              label: 'Urgent tickets',
              value: urgent.length,
              detail: 'Critical or high',
              tone: 'critical',
            },
            {
              label: 'SLA risk',
              value: atRisk.length,
              detail: 'Needs attention',
              tone: 'warning',
            },
            {
              label: 'Unassigned',
              value: unassigned.length,
              detail: 'Available to claim',
            },
          ]
        : role === 'IT_MANAGER'
          ? [
              {
                label: 'Open tickets',
                value: analytics.data?.summary.open_tickets ?? '—',
                detail: 'Organization scope',
              },
              {
                label: 'SLA at risk',
                value: analytics.data?.summary.sla_at_risk ?? '—',
                detail: 'Approaching target',
                tone: 'warning',
              },
              {
                label: 'SLA breached',
                value: analytics.data?.summary.sla_breached ?? '—',
                detail: 'Requires escalation',
                tone: 'critical',
              },
              {
                label: 'Open incidents',
                value: analytics.data?.summary.active_incidents ?? '—',
                detail: 'Active operations',
              },
            ]
          : [
              {
                label: 'Online devices',
                value: analytics.data?.summary.online_devices ?? '—',
                detail: 'Reporting normally',
                tone: 'positive',
              },
              {
                label: 'Offline devices',
                value: analytics.data?.summary.offline_devices ?? '—',
                detail: 'Needs investigation',
                tone: 'warning',
              },
              {
                label: 'Critical alerts',
                value: analytics.data?.summary.critical_alerts ?? '—',
                detail: 'Active signals',
                tone: 'critical',
              },
              {
                label: 'Open tickets',
                value: analytics.data?.summary.open_tickets ?? '—',
                detail: 'Across the service desk',
              },
            ]

  const attention =
    analytics.data?.attention.urgent_tickets ?? urgent.slice(0, 5)

  return (
    <main className="foundation-shell dashboard-page">
      <header className="dashboard-heading">
        <div>
          <p className="eyebrow">Today · Live workspace</p>
          <h1>{titles[role][0]}</h1>
          <p>{titles[role][1]}</p>
        </div>
        {user?.permissions.includes('ticket:create') && (
          <Link className="primary-action" to="/tickets?create=1">
            Create ticket
          </Link>
        )}
      </header>

      <section className="dashboard-metrics" aria-label="Current priorities">
        {metrics.map((item) => (
          <article
            className={item.tone ? `metric-${item.tone}` : undefined}
            key={item.label}
          >
            <span>{item.label}</span>
            <strong>{item.value}</strong>
            <small>{item.detail}</small>
          </article>
        ))}
      </section>

      <div className="dashboard-layout">
        <section className="dashboard-section attention-panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Attention</p>
              <h2>
                {role === 'EMPLOYEE' ? 'Recent requests' : 'Priority queue'}
              </h2>
            </div>
            <Link to="/tickets">View all tickets</Link>
          </div>
          {tickets.isPending && !analytics.data && (
            <p className="dashboard-empty">Loading current work…</p>
          )}
          {!attention.length && !tickets.isPending ? (
            <p className="dashboard-empty">
              Nothing requires immediate attention.
            </p>
          ) : (
            <ol className="attention-list">
              {attention.map((ticket) => (
                <li key={ticket.id}>
                  <Link to={`/tickets/${ticket.id}`}>
                    <span>
                      <strong>{ticket.reference}</strong>
                      <small>{ticket.title}</small>
                    </span>
                    <span
                      className={`priority-badge priority-${ticket.priority.toLowerCase()}`}
                    >
                      {ticket.priority}
                    </span>
                    <span className="status-badge">
                      {ticket.status.replaceAll('_', ' ')}
                    </span>
                  </Link>
                </li>
              ))}
            </ol>
          )}
        </section>

        <aside className="dashboard-section quick-actions">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Workspace</p>
              <h2>Quick access</h2>
            </div>
          </div>
          <nav aria-label="Dashboard shortcuts">
            <Link to="/tickets">
              <span>Ticket queue</span>
              <small>Review and update requests</small>
            </Link>
            {user?.permissions.includes('analytics:view') && (
              <Link to="/analytics">
                <span>Command center</span>
                <small>Workload, SLA, and trends</small>
              </Link>
            )}
            {user?.permissions.includes('alert:view') && (
              <Link to="/alerts">
                <span>Alerts</span>
                <small>Operational signals and notifications</small>
              </Link>
            )}
            {user?.permissions.includes('monitoring:view') && (
              <Link to="/monitoring">
                <span>Device monitoring</span>
                <small>Endpoint health and telemetry</small>
              </Link>
            )}
            {user?.permissions.includes('role:view') && (
              <Link to="/administration/access">
                <span>Access management</span>
                <small>Roles and permissions</small>
              </Link>
            )}
            <Link to="/knowledge">
              <span>Knowledge base</span>
              <small>Trusted operational guidance</small>
            </Link>
          </nav>
        </aside>
      </div>
    </main>
  )
}
