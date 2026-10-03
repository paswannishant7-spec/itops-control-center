import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { errorMessage } from '../../api/client'
import { useAuth } from '../auth/authContextValue'
import {
  createVersion,
  getArticle,
  getEvents,
  getVersions,
  indexArticle,
  transitionArticle,
  type ArticleStatus,
} from './knowledgeApi'
import './knowledge.css'

export function KnowledgeArticlePage() {
  const { articleId = '' } = useParams()
  const { accessToken, user } = useAuth()
  const queryClient = useQueryClient()
  const article = useQuery({
    queryKey: ['knowledge-article', articleId],
    queryFn: ({ signal }) => getArticle(accessToken, articleId, signal),
    enabled: Boolean(articleId),
  })
  const canUpdate = user?.permissions.includes('knowledge:update') ?? false
  const canReview = user?.permissions.includes('knowledge:review') ?? false
  const versions = useQuery({
    queryKey: ['knowledge-versions', articleId],
    queryFn: ({ signal }) => getVersions(accessToken, articleId, signal),
    enabled: canUpdate && Boolean(articleId),
  })
  const events = useQuery({
    queryKey: ['knowledge-events', articleId],
    queryFn: ({ signal }) => getEvents(accessToken, articleId, signal),
    enabled: canReview && Boolean(articleId),
  })
  const refresh = () =>
    queryClient.invalidateQueries({
      queryKey: ['knowledge-article', articleId],
    })
  const revise = useMutation({
    mutationFn: (input: Parameters<typeof createVersion>[2]) =>
      createVersion(accessToken, articleId, input),
    onSuccess: () => {
      void refresh()
      void queryClient.invalidateQueries({
        queryKey: ['knowledge-versions', articleId],
      })
    },
  })
  const transition = useMutation({
    mutationFn: ({
      status,
      reason,
    }: {
      status: ArticleStatus
      reason: string
    }) => transitionArticle(accessToken, articleId, status, reason),
    onSuccess: () => {
      void refresh()
      void queryClient.invalidateQueries({
        queryKey: ['knowledge-events', articleId],
      })
    },
  })
  const indexing = useMutation({
    mutationFn: () => indexArticle(accessToken, articleId),
  })

  if (article.isLoading)
    return (
      <main className="knowledge-shell">
        <p>Loading article…</p>
      </main>
    )
  if (article.isError)
    return (
      <main className="knowledge-shell">
        <section className="knowledge-notice" role="alert">
          <p>{errorMessage(article.error)}</p>
          <button onClick={() => void article.refetch()}>Retry</button>
        </section>
      </main>
    )
  if (!article.data) return null
  const item = article.data
  const isOwner = item.owner.id === user?.id
  const targets: Array<[ArticleStatus, string]> = []
  if (item.status === 'DRAFT' && canUpdate && isOwner)
    targets.push(['IN_REVIEW', 'Submit for review'])
  if (item.status === 'IN_REVIEW' && canReview)
    targets.push(['DRAFT', 'Request changes'])
  if (
    item.status === 'IN_REVIEW' &&
    user?.permissions.includes('knowledge:publish')
  )
    targets.push(['PUBLISHED', 'Publish article'])
  if (
    item.status === 'PUBLISHED' &&
    user?.permissions.includes('knowledge:archive')
  )
    targets.push(['ARCHIVED', 'Archive article'])
  if (item.status === 'ARCHIVED' && canReview)
    targets.push(['DRAFT', 'Restore as draft'])

  function submitRevision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    revise.mutate({
      title: String(data.get('title')),
      summary: String(data.get('summary')),
      content: String(data.get('content')),
      change_summary: String(data.get('change_summary')),
    })
  }
  function submitTransition(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    transition.mutate({
      status: String(data.get('status')) as ArticleStatus,
      reason: String(data.get('reason')),
    })
  }

  return (
    <main className="knowledge-shell article-reader">
      <header className="reader-header">
        <div>
          <Link to="/knowledge" className="back-link">
            ← Knowledge base
          </Link>
          <p className="eyebrow">{item.category.name}</p>
          <h1>{item.version.title}</h1>
          <p>{item.version.summary}</p>
        </div>
        <div className="reader-meta">
          <span
            className={`knowledge-status status-${item.status.toLowerCase()}`}
          >
            {item.status.replace('_', ' ')}
          </span>
          <span>Version {item.version.version}</span>
          <span>Owner {item.owner.display_name}</span>
          {item.published_at && (
            <span>
              Published {new Date(item.published_at).toLocaleDateString()}
            </span>
          )}
        </div>
      </header>
      <div className="reader-layout">
        <article className="knowledge-content">{item.version.content}</article>
        <aside>
          <h2>Article details</h2>
          <p className="tag-row">
            {item.tags.map((tag) => (
              <span key={tag}>{tag}</span>
            ))}
          </p>
          {targets.length > 0 && (
            <form onSubmit={submitTransition}>
              <h3>Workflow</h3>
              <label>
                Action
                <select name="status">
                  {targets.map(([value, label]) => (
                    <option value={value} key={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Reason
                <textarea name="reason" minLength={3} required />
              </label>
              {transition.isError && (
                <p role="alert">{errorMessage(transition.error)}</p>
              )}
              <button disabled={transition.isPending}>Apply action</button>
            </form>
          )}
          {item.status === 'PUBLISHED' &&
            user?.permissions.includes('knowledge:publish') && (
              <section className="knowledge-indexing">
                <h3>AI retrieval index</h3>
                <p>
                  Index this exact published version for grounded
                  troubleshooting.
                </p>
                {indexing.isError && (
                  <p role="alert">{errorMessage(indexing.error)}</p>
                )}
                {indexing.data && (
                  <p role="status">
                    Version {indexing.data.article_version}:{' '}
                    {indexing.data.chunks} chunks ·{' '}
                    {indexing.data.embeddings_created} embedded ·{' '}
                    {indexing.data.embeddings_reused} reused
                  </p>
                )}
                <button
                  type="button"
                  onClick={() => indexing.mutate()}
                  disabled={indexing.isPending}
                >
                  {indexing.isPending ? 'Indexing…' : 'Index published version'}
                </button>
              </section>
            )}
        </aside>
      </div>
      {canUpdate && isOwner && item.status === 'DRAFT' && (
        <form className="revision-form" onSubmit={submitRevision}>
          <h2>Create a new version</h2>
          <label>
            Title
            <input name="title" defaultValue={item.version.title} required />
          </label>
          <label>
            Summary
            <textarea
              name="summary"
              defaultValue={item.version.summary}
              required
            />
          </label>
          <label>
            Content
            <textarea
              name="content"
              defaultValue={item.version.content}
              minLength={10}
              rows={10}
              required
            />
          </label>
          <label>
            Change summary
            <input name="change_summary" minLength={3} required />
          </label>
          {revise.isError && <p role="alert">{errorMessage(revise.error)}</p>}
          <button disabled={revise.isPending}>Save new version</button>
        </form>
      )}
      {canUpdate && versions.data && (
        <section className="history-panel">
          <h2>Version history</h2>
          <ol>
            {versions.data.map((version) => (
              <li key={version.id}>
                <strong>
                  v{version.version} · {version.change_summary}
                </strong>
                <span>
                  {version.author.display_name} ·{' '}
                  {new Date(version.created_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}
      {canReview && events.data && (
        <section className="history-panel">
          <h2>Workflow history</h2>
          <ol>
            {events.data.map((event) => (
              <li key={event.id}>
                <strong>
                  {event.action.replace('knowledge.', '').replace('_', ' ')}
                </strong>
                <span>
                  {event.actor.display_name} · {event.reason}
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}
    </main>
  )
}
