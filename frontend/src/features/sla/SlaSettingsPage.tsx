import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage } from '../../api/client'
import { useAuth } from '../auth/authContextValue'
import { slaApi } from './slaApi'
import './sla.css'

const priorities = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']

export function SlaSettingsPage() {
  const { user, accessToken } = useAuth()
  const queryClient = useQueryClient()
  const [notice, setNotice] = useState<string | null>(null)
  const canManage = user?.permissions.includes('sla:manage') ?? false
  const matrix = useQuery({
    queryKey: ['sla-matrix', user?.id],
    queryFn: ({ signal }) => slaApi.matrix(accessToken, signal),
    retry: false,
  })
  const calendars = useQuery({
    queryKey: ['sla-calendars', user?.id],
    queryFn: ({ signal }) => slaApi.calendars(accessToken, signal),
    retry: false,
  })
  const policies = useQuery({
    queryKey: ['sla-policies', user?.id],
    queryFn: ({ signal }) => slaApi.policies(accessToken, signal),
    retry: false,
  })
  const updateMatrix = useMutation({
    mutationFn: (values: {
      impact: string
      urgency: string
      priority: string
    }) =>
      slaApi.setMatrix(
        accessToken,
        values.impact,
        values.urgency,
        values.priority,
      ),
    onSuccess: () => {
      setNotice('Priority rule saved.')
      void queryClient.invalidateQueries({ queryKey: ['sla-matrix'] })
    },
  })
  const createCalendar = useMutation({
    mutationFn: (body: object) => slaApi.createCalendar(accessToken, body),
    onSuccess: () => {
      setNotice('Business calendar created.')
      void queryClient.invalidateQueries({ queryKey: ['sla-calendars'] })
    },
  })
  const createPolicy = useMutation({
    mutationFn: (body: object) => slaApi.createPolicy(accessToken, body),
    onSuccess: () => {
      setNotice('SLA policy created and activated.')
      void queryClient.invalidateQueries({ queryKey: ['sla-policies'] })
    },
  })
  const failure =
    matrix.error ??
    calendars.error ??
    policies.error ??
    updateMatrix.error ??
    createCalendar.error ??
    createPolicy.error

  function submitCalendar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setNotice(null)
    const form = event.currentTarget
    const values = Object.fromEntries(new FormData(form))
    const start = Number(values.start_hour) * 60
    const end = Number(values.end_hour) * 60
    createCalendar.mutate(
      {
        name: values.name,
        timezone: values.timezone,
        is_default: values.is_default === 'on',
        windows: [0, 1, 2, 3, 4].map((weekday) => ({
          weekday,
          start_minute: start,
          end_minute: end,
        })),
        holidays: [],
      },
      { onSuccess: () => form.reset() },
    )
  }

  function submitPolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setNotice(null)
    const form = event.currentTarget
    const values = Object.fromEntries(new FormData(form))
    createPolicy.mutate(
      {
        name: values.name,
        priority: values.priority,
        calendar_id: values.calendar_id,
        response_target_minutes: Number(values.response_target_minutes),
        resolution_target_minutes: Number(values.resolution_target_minutes),
        at_risk_percent: Number(values.at_risk_percent),
      },
      { onSuccess: () => form.reset() },
    )
  }

  return (
    <main className="sla-settings">
      <header className="ticket-topbar">
        <Link className="brand" to="/">
          ← Workspace
        </Link>
        <Link to="/tickets">Ticket queue</Link>
      </header>
      <section className="tickets-heading">
        <div>
          <p className="eyebrow">Administration · Service levels</p>
          <h1>Priority and SLA policy</h1>
          <p>
            Control urgency mapping, working time, and response and resolution
            targets.
          </p>
        </div>
      </section>
      {(notice || failure) && (
        <p
          className={
            failure
              ? 'ticket-error page-message'
              : 'ticket-success page-message'
          }
          role={failure ? 'alert' : 'status'}
        >
          {failure ? errorMessage(failure) : notice}
        </p>
      )}
      {(matrix.isPending || calendars.isPending || policies.isPending) && (
        <p className="ticket-state">Loading SLA configuration…</p>
      )}
      <section className="ticket-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Impact × urgency</p>
            <h2>Priority matrix</h2>
          </div>
          <span>{matrix.data?.length ?? 0} rules</span>
        </div>
        <div className="matrix-grid">
          {matrix.data?.map((entry) => (
            <label key={`${entry.impact}-${entry.urgency}`}>
              {entry.impact} impact · {entry.urgency} urgency
              <select
                value={entry.priority}
                disabled={!canManage || updateMatrix.isPending}
                onChange={(event) =>
                  updateMatrix.mutate({
                    ...entry,
                    priority: event.target.value,
                  })
                }
              >
                {priorities.map((priority) => (
                  <option key={priority}>{priority}</option>
                ))}
              </select>
            </label>
          ))}
        </div>
      </section>
      <div className="sla-config-grid">
        <section className="ticket-panel">
          <div className="panel-heading">
            <h2>Business calendars</h2>
            <span>{calendars.data?.length ?? 0}</span>
          </div>
          <ul className="config-list">
            {calendars.data?.map((calendar) => (
              <li key={calendar.id}>
                <strong>{calendar.name}</strong>
                <span>
                  {calendar.timezone} · {calendar.windows.length} windows
                  {calendar.is_default ? ' · Default' : ''}
                </span>
              </li>
            ))}
          </ul>
          {canManage && (
            <form className="side-form" onSubmit={submitCalendar}>
              <h3>Create weekday calendar</h3>
              <label>
                Name
                <input name="name" minLength={2} required />
              </label>
              <label>
                Timezone
                <input name="timezone" defaultValue="UTC" required />
              </label>
              <div className="field-pair">
                <label>
                  Start hour
                  <input
                    name="start_hour"
                    type="number"
                    min="0"
                    max="23"
                    defaultValue="9"
                    required
                  />
                </label>
                <label>
                  End hour
                  <input
                    name="end_hour"
                    type="number"
                    min="1"
                    max="24"
                    defaultValue="17"
                    required
                  />
                </label>
              </div>
              <label className="checkbox-line">
                <input name="is_default" type="checkbox" /> Make default
                calendar
              </label>
              <button disabled={createCalendar.isPending}>
                Create calendar
              </button>
            </form>
          )}
        </section>
        <section className="ticket-panel">
          <div className="panel-heading">
            <h2>SLA policies</h2>
            <span>{policies.data?.length ?? 0}</span>
          </div>
          <ul className="config-list">
            {policies.data?.map((policy) => (
              <li key={policy.id}>
                <strong>{policy.name}</strong>
                <span>
                  {policy.priority} · response {policy.response_target_minutes}m
                  · resolution {policy.resolution_target_minutes}m · risk{' '}
                  {policy.at_risk_percent}%
                </span>
              </li>
            ))}
          </ul>
          {canManage && calendars.data?.length ? (
            <form className="side-form" onSubmit={submitPolicy}>
              <h3>Create active policy</h3>
              <label>
                Name
                <input name="name" minLength={2} required />
              </label>
              <label>
                Priority
                <select name="priority">
                  {priorities.map((priority) => (
                    <option key={priority}>{priority}</option>
                  ))}
                </select>
              </label>
              <label>
                Calendar
                <select name="calendar_id">
                  {calendars.data
                    .filter((item) => item.is_active)
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Response minutes
                <input
                  name="response_target_minutes"
                  type="number"
                  min="1"
                  defaultValue="60"
                  required
                />
              </label>
              <label>
                Resolution minutes
                <input
                  name="resolution_target_minutes"
                  type="number"
                  min="1"
                  defaultValue="480"
                  required
                />
              </label>
              <label>
                At-risk percentage
                <input
                  name="at_risk_percent"
                  type="number"
                  min="1"
                  max="99"
                  defaultValue="80"
                  required
                />
              </label>
              <button disabled={createPolicy.isPending}>Create policy</button>
            </form>
          ) : null}
        </section>
      </div>
    </main>
  )
}
