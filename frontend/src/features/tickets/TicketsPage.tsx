import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { z } from 'zod'
import { errorMessage } from '../../api/client'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { useAuth } from '../auth/authContextValue'
import { ticketApi } from './ticketApi'
import { assetApi } from '../assets/assetApi'
import './tickets.css'

const createSchema = z.object({
  title: z.string().trim().min(5).max(200),
  description: z.string().trim().min(10).max(20_000),
  impact: z.enum(['LOW', 'MEDIUM', 'HIGH']),
  urgency: z.enum(['LOW', 'MEDIUM', 'HIGH']),
  asset_id: z.string().uuid().optional(),
})

function displayDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

export function TicketsPage() {
  const { user, accessToken } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState(searchParams.get('search') ?? '')
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const [slaState, setSlaState] = useState('')
  const [offset, setOffset] = useState(0)
  const [showCreate, setShowCreate] = useState(
    searchParams.get('create') === '1',
  )
  const [formError, setFormError] = useState<string | null>(null)
  const debouncedSearch = useDebouncedValue(search.trim())
  const canCreate = user?.permissions.includes('ticket:create') ?? false
  const query = new URLSearchParams({ offset: String(offset), limit: '25' })
  if (debouncedSearch) query.set('search', debouncedSearch)
  if (status) query.set('status', status)
  if (priority) query.set('priority', priority)
  if (slaState) query.set('sla_state', slaState)
  const tickets = useQuery({
    queryKey: ['tickets', user?.id, query.toString()],
    queryFn: ({ signal }) =>
      ticketApi.list(accessToken, query.toString(), signal),
    retry: false,
  })
  const assets = useQuery({
    queryKey: ['assets', 'ticket-intake'],
    queryFn: ({ signal }) =>
      assetApi.list(accessToken, 'status=ACTIVE&offset=0&limit=100', signal),
    enabled: canCreate && showCreate,
    retry: false,
  })
  const createTicket = useMutation({
    mutationFn: (body: z.infer<typeof createSchema>) =>
      ticketApi.create(accessToken, body),
    onSuccess: (ticket) => {
      void queryClient.invalidateQueries({ queryKey: ['tickets'] })
      void navigate(`/tickets/${ticket.id}`)
    },
  })
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFormError(null)
    const data = new FormData(event.currentTarget)
    const values = Object.fromEntries(data)
    if (!values.asset_id) delete values.asset_id
    const parsed = createSchema.safeParse(values)
    if (!parsed.success) {
      setFormError('Enter a title and a description of at least 10 characters.')
      return
    }
    createTicket.mutate(parsed.data)
  }

  return (
    <main className="tickets-page">
      <header className="ticket-topbar">
        <Link className="brand" to="/">
          ← Workspace
        </Link>
        <div>
          {user?.permissions.includes('team:view') && (
            <Link to="/directory">People & teams</Link>
          )}
          {user?.permissions.includes('sla:view') && (
            <Link to="/administration/sla">SLA policies</Link>
          )}
          <Link to="/assets">Assets</Link>
          <span>{user?.display_name}</span>
        </div>
      </header>
      <section className="tickets-heading">
        <div>
          <p className="eyebrow">Service desk · Ticket core</p>
          <h1>Support queue</h1>
          <p>
            Track requests from intake through a controlled resolution workflow.
          </p>
        </div>
        {canCreate && (
          <button
            type="button"
            onClick={() => setShowCreate((value) => !value)}
          >
            {showCreate ? 'Close form' : 'Create ticket'}
          </button>
        )}
      </section>

      {showCreate && (
        <section
          className="ticket-panel create-ticket"
          aria-labelledby="create-ticket-heading"
        >
          <h2 id="create-ticket-heading">New support request</h2>
          <form onSubmit={submit}>
            <label>
              Title
              <input name="title" minLength={5} maxLength={200} required />
            </label>
            <label className="wide-field">
              Description
              <textarea
                name="description"
                minLength={10}
                maxLength={20_000}
                required
                rows={5}
              />
            </label>
            <label>
              Impact
              <select name="impact" defaultValue="MEDIUM">
                <option value="LOW">Low</option>
                <option value="MEDIUM">Medium</option>
                <option value="HIGH">High</option>
              </select>
            </label>
            <label>
              Urgency
              <select name="urgency" defaultValue="MEDIUM">
                <option value="LOW">Low</option>
                <option value="MEDIUM">Medium</option>
                <option value="HIGH">High</option>
              </select>
            </label>
            <label className="wide-field">
              Related asset
              <select name="asset_id" defaultValue="">
                <option value="">No asset</option>
                {assets.data?.items.map((asset) => (
                  <option key={asset.id} value={asset.id}>
                    {asset.asset_tag} ·{' '}
                    {asset.hostname ?? asset.model ?? asset.asset_type}
                  </option>
                ))}
              </select>
            </label>
            {(formError || createTicket.error) && (
              <p role="alert" className="ticket-error wide-field">
                {formError ?? errorMessage(createTicket.error)}
              </p>
            )}
            <button type="submit" disabled={createTicket.isPending}>
              {createTicket.isPending ? 'Creating…' : 'Submit request'}
            </button>
          </form>
        </section>
      )}

      <section className="ticket-panel" aria-labelledby="queue-heading">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">Visible to you</p>
            <h2 id="queue-heading">Ticket queue</h2>
          </div>
          {tickets.data && <span>{tickets.data.total} tickets</span>}
        </div>
        <div className="ticket-filters">
          <label>
            Search
            <input
              value={search}
              onChange={(event) => {
                setSearch(event.target.value)
                setOffset(0)
              }}
              placeholder="Reference, title, or description"
            />
          </label>
          <label>
            Status
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">All statuses</option>
              {[
                'NEW',
                'OPEN',
                'IN_PROGRESS',
                'PENDING_USER',
                'PENDING_VENDOR',
                'ESCALATED',
                'RESOLVED',
                'CLOSED',
                'CANCELLED',
              ].map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label>
            Priority
            <select
              value={priority}
              onChange={(event) => setPriority(event.target.value)}
            >
              <option value="">All priorities</option>
              {['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label>
            SLA state
            <select
              value={slaState}
              onChange={(event) => {
                setSlaState(event.target.value)
                setOffset(0)
              }}
            >
              <option value="">All SLA states</option>
              {['ON_TRACK', 'AT_RISK', 'BREACHED', 'PAUSED', 'COMPLETED'].map(
                (value) => (
                  <option key={value}>{value}</option>
                ),
              )}
            </select>
          </label>
        </div>
        {tickets.isPending && (
          <p className="ticket-state" aria-live="polite">
            Loading tickets…
          </p>
        )}
        {tickets.error && (
          <div className="ticket-state" role="alert">
            <p>{errorMessage(tickets.error)}</p>
            <button type="button" onClick={() => void tickets.refetch()}>
              Retry
            </button>
          </div>
        )}
        {tickets.data?.total === 0 && (
          <p className="ticket-state">
            No tickets match this view. Create a request or adjust the filters.
          </p>
        )}
        {!!tickets.data?.items.length && (
          <div className="ticket-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Ticket</th>
                  <th>Status</th>
                  <th>Priority</th>
                  <th>SLA</th>
                  <th>Requester</th>
                  <th>Assignment</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {tickets.data.items.map((ticket) => (
                  <tr key={ticket.id}>
                    <td>
                      <Link to={`/tickets/${ticket.id}`}>
                        <strong>{ticket.reference}</strong>
                      </Link>
                      <span>{ticket.title}</span>
                    </td>
                    <td>
                      <span className="status-badge">
                        {ticket.status.replaceAll('_', ' ')}
                      </span>
                    </td>
                    <td>
                      <span
                        className={`priority-badge priority-${ticket.priority.toLowerCase()}`}
                      >
                        {ticket.priority}
                      </span>
                    </td>
                    <td>
                      <span className="sla-badge">
                        {ticket.sla_state?.replaceAll('_', ' ') ??
                          'Not configured'}
                      </span>
                    </td>
                    <td>{ticket.requester.display_name}</td>
                    <td>
                      {ticket.assigned_technician?.display_name ??
                        ticket.assignment_team?.name ??
                        'Unassigned'}
                    </td>
                    <td>{displayDate(ticket.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {tickets.data && tickets.data.total > tickets.data.limit && (
          <div className="pagination" aria-label="Ticket pages">
            <button
              type="button"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 25))}
            >
              Previous
            </button>
            <span>
              {offset + 1}–{Math.min(offset + 25, tickets.data.total)} of{' '}
              {tickets.data.total}
            </span>
            <button
              type="button"
              disabled={offset + 25 >= tickets.data.total}
              onClick={() => setOffset(offset + 25)}
            >
              Next
            </button>
          </div>
        )}
      </section>
    </main>
  )
}
