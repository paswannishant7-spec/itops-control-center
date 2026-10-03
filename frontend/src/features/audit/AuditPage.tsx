import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { z } from 'zod'
import { errorMessage } from '../../api/client'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { useAuth } from '../auth/authContextValue'
import { auditApi, auditSourceSchema } from './auditApi'
import './audit.css'

const sources = auditSourceSchema.options
const pageSize = 50

export function AuditPage() {
  const { accessToken } = useAuth()
  const [source, setSource] = useState('')
  const [action, setAction] = useState('')
  const [entityId, setEntityId] = useState('')
  const [offset, setOffset] = useState(0)
  const debouncedAction = useDebouncedValue(action.trim())
  const debouncedEntityId = useDebouncedValue(entityId.trim())
  const entityIdValid =
    !debouncedEntityId || z.string().uuid().safeParse(debouncedEntityId).success
  const query = new URLSearchParams({
    offset: String(offset),
    limit: String(pageSize),
  })
  if (source) query.set('source', source)
  if (debouncedAction) query.set('action', debouncedAction)
  if (debouncedEntityId && entityIdValid)
    query.set('entity_id', debouncedEntityId)
  const events = useQuery({
    queryKey: [
      'audit-events',
      source,
      debouncedAction,
      debouncedEntityId,
      offset,
    ],
    queryFn: ({ signal }) => auditApi.events(accessToken, query, signal),
    enabled: entityIdValid,
    retry: false,
  })

  const clearFilters = () => {
    setSource('')
    setAction('')
    setEntityId('')
    setOffset(0)
  }

  return (
    <main className="audit-page">
      <header>
        <div>
          <p className="eyebrow">Administration · Security</p>
          <h1>Audit trail</h1>
        </div>
        <Link to="/">Back to operations</Link>
      </header>
      <section className="audit-filters" aria-label="Audit filters">
        <label>
          Source
          <select
            value={source}
            onChange={(event) => {
              setSource(event.target.value)
              setOffset(0)
            }}
          >
            <option value="">All sources</option>
            {sources.map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          Exact action
          <input
            type="search"
            value={action}
            onChange={(event) => {
              setAction(event.target.value)
              setOffset(0)
            }}
          />
        </label>
        <label>
          Entity UUID
          <input
            value={entityId}
            onChange={(event) => {
              setEntityId(event.target.value)
              setOffset(0)
            }}
            aria-invalid={!entityIdValid}
            aria-describedby={!entityIdValid ? 'entity-id-error' : undefined}
          />
        </label>
      </section>
      {!entityIdValid && (
        <p id="entity-id-error" className="audit-error" role="alert">
          Enter a valid entity UUID or leave the field blank.
        </p>
      )}
      {events.isPending && entityIdValid && (
        <p role="status">Loading immutable activity…</p>
      )}
      {events.isError && (
        <div className="audit-error" role="alert">
          <p>{errorMessage(events.error)}</p>
          <button type="button" onClick={() => void events.refetch()}>
            Retry
          </button>
        </div>
      )}
      {events.data && (
        <>
          <p>{events.data.total.toLocaleString()} matching events</p>
          <div className="audit-table-wrap">
            <table>
              <caption className="sr-only">Immutable audit events</caption>
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Source</th>
                  <th scope="col">Action</th>
                  <th scope="col">Entity</th>
                  <th scope="col">Actor</th>
                  <th scope="col">Reason</th>
                  <th scope="col">Changes</th>
                </tr>
              </thead>
              <tbody>
                {events.data.items.map((event) => (
                  <tr key={event.id}>
                    <td>
                      <time dateTime={event.created_at}>
                        {new Date(event.created_at).toLocaleString()}
                      </time>
                    </td>
                    <td>{event.source}</td>
                    <td>
                      <code>{event.action}</code>
                    </td>
                    <td>
                      {event.entity_type}
                      <small>{event.entity_id}</small>
                    </td>
                    <td>{event.actor_id ?? 'System'}</td>
                    <td>{event.reason}</td>
                    <td>
                      <details>
                        <summary>Inspect</summary>
                        <pre>
                          {JSON.stringify(
                            {
                              before: event.before_state,
                              after: event.after_state,
                              request_id: event.request_id,
                            },
                            null,
                            2,
                          )}
                        </pre>
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!events.data.items.length && (
            <div className="audit-empty">
              <p>No audit events match these filters.</p>
              <button type="button" onClick={clearFilters}>
                Clear filters
              </button>
            </div>
          )}
          <nav className="audit-pagination" aria-label="Audit pages">
            <button
              type="button"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - pageSize))}
            >
              Previous
            </button>
            <button
              type="button"
              disabled={offset + pageSize >= events.data.total}
              onClick={() => setOffset(offset + pageSize)}
            >
              Next
            </button>
          </nav>
        </>
      )}
    </main>
  )
}
