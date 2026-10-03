import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { errorMessage } from '../../api/client'
import { useAuth } from '../auth/authContextValue'
import { directoryApi } from '../directory/directoryApi'
import { ticketApi } from './ticketApi'
import type {
  AssistantResponse,
  AssistantTask,
  FeedbackAction,
} from './ticketApi'
import './tickets.css'

const transitions: Record<string, string[]> = {
  NEW: ['OPEN'],
  OPEN: ['IN_PROGRESS', 'CANCELLED'],
  IN_PROGRESS: ['PENDING_USER', 'PENDING_VENDOR', 'ESCALATED', 'RESOLVED'],
  PENDING_USER: ['IN_PROGRESS'],
  PENDING_VENDOR: ['IN_PROGRESS'],
  ESCALATED: ['IN_PROGRESS'],
  RESOLVED: ['CLOSED', 'OPEN'],
  CLOSED: [],
  CANCELLED: [],
}

function requiredPermission(current: string, target: string) {
  if (target === 'ESCALATED') return 'ticket:escalate'
  if (target === 'RESOLVED') return 'ticket:resolve'
  if (target === 'CLOSED') return 'ticket:close'
  if (current === 'RESOLVED' && target === 'OPEN') return 'ticket:reopen'
  return 'ticket:update'
}

function displayDate(value: string | null) {
  if (!value) return 'Not recorded'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

function displayDuration(seconds: number) {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.ceil((seconds % 3600) / 60)
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`
}

export function TicketDetailPage() {
  const { ticketId = '' } = useParams()
  const { user, accessToken } = useAuth()
  const canUseAI = user?.permissions.includes('ai:use') ?? false
  const queryClient = useQueryClient()
  const [selectedTeam, setSelectedTeam] = useState('')
  const [actionMessage, setActionMessage] = useState<string | null>(null)
  const [downloadError, setDownloadError] = useState<Error | null>(null)
  const [replyBody, setReplyBody] = useState('')
  const [draftEdit, setDraftEdit] = useState<{
    recommendationId: string
    value: string
  } | null>(null)
  const [feedbackNote, setFeedbackNote] = useState('')
  const ticket = useQuery({
    queryKey: ['ticket', ticketId, user?.id],
    queryFn: ({ signal }) => ticketApi.get(accessToken, ticketId, signal),
    retry: false,
  })
  const comments = useQuery({
    queryKey: ['ticket-comments', ticketId, user?.id],
    queryFn: ({ signal }) => ticketApi.comments(accessToken, ticketId, signal),
    retry: false,
  })
  const sla = useQuery({
    queryKey: ['ticket-sla', ticketId, user?.id],
    queryFn: ({ signal }) => ticketApi.sla(accessToken, ticketId, signal),
    retry: false,
  })
  const events = useQuery({
    queryKey: ['ticket-events', ticketId, user?.id],
    queryFn: ({ signal }) => ticketApi.events(accessToken, ticketId, signal),
    retry: false,
  })
  const attachments = useQuery({
    queryKey: ['ticket-attachments', ticketId, user?.id],
    queryFn: ({ signal }) =>
      ticketApi.attachments(accessToken, ticketId, signal),
    retry: false,
  })
  const classification = useQuery({
    queryKey: ['ticket-classification', ticketId, user?.id],
    queryFn: ({ signal }) =>
      ticketApi.latestClassification(accessToken, ticketId, signal),
    enabled: canUseAI,
    retry: false,
  })
  const troubleshooting = useQuery({
    queryKey: ['ticket-troubleshooting', ticketId, user?.id],
    queryFn: ({ signal }) =>
      ticketApi.latestTroubleshooting(accessToken, ticketId, signal),
    enabled: canUseAI,
    retry: false,
  })
  const responseDraft = useQuery({
    queryKey: ['ticket-assistant', ticketId, 'RESPONSE_DRAFT', user?.id],
    queryFn: ({ signal }) =>
      ticketApi.latestAssistant(
        accessToken,
        ticketId,
        'RESPONSE_DRAFT',
        signal,
      ),
    enabled: canUseAI,
    retry: false,
  })
  const ticketSummary = useQuery({
    queryKey: ['ticket-assistant', ticketId, 'SUMMARIZATION', user?.id],
    queryFn: ({ signal }) =>
      ticketApi.latestAssistant(accessToken, ticketId, 'SUMMARIZATION', signal),
    enabled: canUseAI,
    retry: false,
  })
  const similarTickets = useQuery({
    queryKey: ['similar-tickets', ticketId, user?.id],
    queryFn: () => ticketApi.similar(accessToken, ticketId),
    enabled: canUseAI,
    retry: false,
  })
  const canAssign =
    user?.permissions.some((permission) =>
      ['ticket:assign', 'ticket:reassign'].includes(permission),
    ) ?? false
  const teams = useQuery({
    queryKey: ['ticket-assignment-teams', user?.id],
    queryFn: ({ signal }) => directoryApi.teams(accessToken, signal),
    enabled: canAssign && (user?.permissions.includes('team:view') ?? false),
    retry: false,
  })
  const teamDetail = useQuery({
    queryKey: ['ticket-assignment-team', selectedTeam],
    queryFn: ({ signal }) =>
      directoryApi.team(accessToken, selectedTeam, signal),
    enabled: Boolean(selectedTeam),
    retry: false,
  })

  function refresh() {
    void queryClient.invalidateQueries({ queryKey: ['ticket', ticketId] })
    void queryClient.invalidateQueries({ queryKey: ['tickets'] })
    void queryClient.invalidateQueries({
      queryKey: ['ticket-events', ticketId],
    })
    void queryClient.invalidateQueries({ queryKey: ['ticket-sla', ticketId] })
  }

  const transition = useMutation({
    mutationFn: (body: object) =>
      ticketApi.transition(accessToken, ticketId, body),
    onSuccess: () => {
      setActionMessage('Status updated.')
      refresh()
    },
  })
  const assign = useMutation({
    mutationFn: (body: object) => ticketApi.assign(accessToken, ticketId, body),
    onSuccess: () => {
      setActionMessage('Assignment updated.')
      refresh()
    },
  })
  const addComment = useMutation({
    mutationFn: (body: object) =>
      ticketApi.addComment(accessToken, ticketId, body),
    onSuccess: () => {
      setActionMessage('Comment added.')
      void queryClient.invalidateQueries({
        queryKey: ['ticket-comments', ticketId],
      })
      refresh()
    },
  })
  const upload = useMutation({
    mutationFn: (file: File) => ticketApi.upload(accessToken, ticketId, file),
    onSuccess: () => {
      setActionMessage('Attachment uploaded.')
      void queryClient.invalidateQueries({
        queryKey: ['ticket-attachments', ticketId],
      })
      refresh()
    },
  })
  const classify = useMutation({
    mutationFn: () => ticketApi.classify(accessToken, ticketId),
    onSuccess: (result) => {
      queryClient.setQueryData(
        ['ticket-classification', ticketId, user?.id],
        result,
      )
    },
  })
  const troubleshoot = useMutation({
    mutationFn: () => ticketApi.troubleshoot(accessToken, ticketId),
    onSuccess: (result) => {
      queryClient.setQueryData(
        ['ticket-troubleshooting', ticketId, user?.id],
        result,
      )
    },
  })
  async function generateAssistant(
    task: AssistantTask,
    current: AssistantResponse | null | undefined,
  ) {
    if (current && !current.feedback) {
      await ticketApi.reviewRecommendation(
        accessToken,
        ticketId,
        current.recommendation_id,
        { action: 'REGENERATED' },
      )
    }
    return ticketApi.generateAssistant(accessToken, ticketId, task)
  }
  const generateDraft = useMutation({
    mutationFn: () => generateAssistant('RESPONSE_DRAFT', responseDraft.data),
    onSuccess: (result) => {
      queryClient.setQueryData(
        ['ticket-assistant', ticketId, 'RESPONSE_DRAFT', user?.id],
        result,
      )
      if (result.task_type === 'RESPONSE_DRAFT')
        setDraftEdit({
          recommendationId: result.recommendation_id,
          value: result.recommendation.draft,
        })
    },
  })
  const generateSummary = useMutation({
    mutationFn: () => generateAssistant('SUMMARIZATION', ticketSummary.data),
    onSuccess: (result) => {
      queryClient.setQueryData(
        ['ticket-assistant', ticketId, 'SUMMARIZATION', user?.id],
        result,
      )
    },
  })
  const reviewRecommendation = useMutation({
    mutationFn: ({
      result,
      action,
      editedContent,
    }: {
      result: AssistantResponse
      action: FeedbackAction
      editedContent?: string
    }) =>
      ticketApi.reviewRecommendation(
        accessToken,
        ticketId,
        result.recommendation_id,
        {
          action,
          ...(feedbackNote.trim()
            ? { feedback_text: feedbackNote.trim() }
            : {}),
          ...(editedContent ? { edited_content: editedContent } : {}),
        },
      ),
    onSuccess: (feedback, variables) => {
      const task = variables.result.task_type
      queryClient.setQueryData<AssistantResponse | null>(
        ['ticket-assistant', ticketId, task, user?.id],
        (current) => (current ? { ...current, feedback } : current),
      )
      if (
        task === 'RESPONSE_DRAFT' &&
        (variables.action === 'ACCEPTED' || variables.action === 'EDITED')
      ) {
        const recommendation = variables.result.recommendation
        if ('draft' in recommendation)
          setReplyBody(variables.editedContent ?? recommendation.draft)
      }
      setFeedbackNote('')
      setActionMessage(
        variables.action === 'ACCEPTED' || variables.action === 'EDITED'
          ? 'AI output reviewed. A draft was copied to the reply composer where applicable.'
          : 'AI feedback recorded.',
      )
    },
  })

  const current = ticket.data
  const draftResult =
    responseDraft.data?.task_type === 'RESPONSE_DRAFT'
      ? responseDraft.data
      : null
  const summaryResult =
    ticketSummary.data?.task_type === 'SUMMARIZATION'
      ? ticketSummary.data
      : null
  const editedDraft =
    draftEdit && draftEdit.recommendationId === draftResult?.recommendation_id
      ? draftEdit.value
      : (draftResult?.recommendation.draft ?? '')
  const nextStatuses = (current ? transitions[current.status] : []).filter(
    (target) =>
      user?.permissions.includes(
        requiredPermission(current?.status ?? '', target),
      ),
  )
  const actionError =
    transition.error ??
    assign.error ??
    addComment.error ??
    upload.error ??
    downloadError

  if (ticket.isPending)
    return (
      <main className="centered-page">
        <p aria-live="polite">Loading ticket workspace…</p>
      </main>
    )
  if (ticket.error || !current)
    return (
      <main className="centered-page">
        <section className="error-panel" role="alert">
          <h1>Ticket unavailable</h1>
          <p>{errorMessage(ticket.error)}</p>
          <button type="button" onClick={() => void ticket.refetch()}>
            Retry
          </button>
          <Link className="button-link" to="/tickets">
            Return to queue
          </Link>
        </section>
      </main>
    )

  function submitTransition(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setActionMessage(null)
    const values = Object.fromEntries(new FormData(event.currentTarget))
    transition.mutate(values)
  }

  function submitAssignment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setActionMessage(null)
    const values = Object.fromEntries(new FormData(event.currentTarget))
    if (!values.technician_id) delete values.technician_id
    assign.mutate(values)
  }

  function submitComment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setActionMessage(null)
    const form = event.currentTarget
    addComment.mutate(Object.fromEntries(new FormData(form)), {
      onSuccess: () => {
        form.reset()
        setReplyBody('')
      },
    })
  }

  return (
    <main className="ticket-workspace">
      <header className="ticket-topbar">
        <Link className="brand" to="/tickets">
          ← Ticket queue
        </Link>
        <span>{user?.display_name}</span>
      </header>
      <section className="ticket-record-header">
        <div>
          <p className="eyebrow">{current.reference}</p>
          <h1>{current.title}</h1>
          <p>
            Opened {displayDate(current.created_at)} by{' '}
            {current.requester.display_name}
          </p>
        </div>
        <div className="record-badges">
          <span className="status-badge">
            {current.status.replaceAll('_', ' ')}
          </span>
          <span
            className={`priority-badge priority-${current.priority.toLowerCase()}`}
          >
            {current.priority} priority
          </span>
        </div>
      </section>
      {(actionMessage !== null || actionError !== null) && (
        <p
          className={
            actionError
              ? 'ticket-error page-message'
              : 'ticket-success page-message'
          }
          role={actionError ? 'alert' : 'status'}
        >
          {actionError ? errorMessage(actionError) : actionMessage}
        </p>
      )}

      <div className="ticket-workspace-grid">
        <div className="ticket-main-column">
          <section className="ticket-panel">
            <div className="panel-heading">
              <h2>Request</h2>
              <span>{current.source}</span>
            </div>
            <p className="ticket-description">{current.description}</p>
            <dl className="record-facts">
              <div>
                <dt>Impact</dt>
                <dd>{current.impact}</dd>
              </div>
              <div>
                <dt>Urgency</dt>
                <dd>{current.urgency}</dd>
              </div>
              <div>
                <dt>Category</dt>
                <dd>{current.category?.name ?? 'Not categorized'}</dd>
              </div>
              <div>
                <dt>Asset</dt>
                <dd>
                  {current.asset_id ? (
                    <Link to={`/assets/${current.asset_id}`}>View asset</Link>
                  ) : (
                    'Not linked'
                  )}
                </dd>
              </div>
            </dl>
          </section>

          <section
            className="ticket-panel"
            aria-labelledby="conversation-heading"
          >
            <div className="panel-heading">
              <h2 id="conversation-heading">Conversation</h2>
              <span>{comments.data?.total ?? 0} messages</span>
            </div>
            {comments.isPending && (
              <p className="ticket-state">Loading conversation…</p>
            )}
            {comments.error && (
              <p role="alert" className="ticket-error">
                {errorMessage(comments.error)}
              </p>
            )}
            {comments.data?.items.length === 0 && (
              <p className="ticket-state">No messages yet.</p>
            )}
            <div className="conversation-list">
              {comments.data?.items.map((comment) => (
                <article
                  key={comment.id}
                  className={
                    comment.visibility === 'INTERNAL' ? 'internal-note' : ''
                  }
                >
                  <div>
                    <strong>{comment.author.display_name}</strong>
                    <span>
                      {comment.visibility === 'INTERNAL'
                        ? 'Internal note'
                        : 'Public reply'}{' '}
                      · {displayDate(comment.created_at)}
                    </span>
                  </div>
                  <p>{comment.body}</p>
                </article>
              ))}
            </div>
            {user?.permissions.includes('ticket:comment') &&
              !['CLOSED', 'CANCELLED'].includes(current.status) && (
                <form className="comment-form" onSubmit={submitComment}>
                  <label>
                    Reply
                    <textarea
                      name="body"
                      required
                      maxLength={10_000}
                      rows={4}
                      value={replyBody}
                      onChange={(event) => setReplyBody(event.target.value)}
                    />
                  </label>
                  {user.permissions.includes('ticket:internal_note') && (
                    <label>
                      Visibility
                      <select name="visibility" defaultValue="PUBLIC">
                        <option value="PUBLIC">Public reply</option>
                        <option value="INTERNAL">Internal note</option>
                      </select>
                    </label>
                  )}
                  <button type="submit" disabled={addComment.isPending}>
                    {addComment.isPending ? 'Sending…' : 'Add message'}
                  </button>
                </form>
              )}
          </section>

          <section
            className="ticket-panel"
            aria-labelledby="attachments-heading"
          >
            <div className="panel-heading">
              <h2 id="attachments-heading">Attachments</h2>
              <span>{attachments.data?.length ?? 0} files</span>
            </div>
            {attachments.error && (
              <p className="ticket-error" role="alert">
                {errorMessage(attachments.error)}
              </p>
            )}
            <ul className="attachment-list">
              {attachments.data?.map((attachment) => (
                <li key={attachment.id}>
                  <button
                    type="button"
                    onClick={() => {
                      setDownloadError(null)
                      void ticketApi
                        .download(accessToken, ticketId, attachment.id)
                        .then((blob) => {
                          const url = URL.createObjectURL(blob)
                          const link = document.createElement('a')
                          link.href = url
                          link.download = attachment.original_name
                          link.click()
                          URL.revokeObjectURL(url)
                        })
                        .catch((error: unknown) =>
                          setDownloadError(
                            error instanceof Error
                              ? error
                              : new Error(errorMessage(error)),
                          ),
                        )
                    }}
                  >
                    {attachment.original_name}
                  </button>
                  <span>
                    {Math.ceil(attachment.size_bytes / 1024)} KB ·{' '}
                    {attachment.content_type}
                  </span>
                </li>
              ))}
            </ul>
            {user?.permissions.includes('ticket:comment') &&
              !['CLOSED', 'CANCELLED'].includes(current.status) && (
                <label className="file-upload">
                  Upload image, PDF, or text file
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/gif,application/pdf,text/plain,.log,.md,.csv,.json"
                    onChange={(event) => {
                      const file = event.target.files?.[0]
                      if (file) upload.mutate(file)
                    }}
                    disabled={upload.isPending}
                  />
                </label>
              )}
          </section>
        </div>

        <aside className="ticket-side-column">
          {canUseAI && (
            <section
              className="ticket-panel ai-insights"
              aria-labelledby="ai-heading"
            >
              <div className="panel-heading">
                <h2 id="ai-heading">AI classification</h2>
                {classification.data && (
                  <span
                    className={`confidence-${classification.data.confidence_band.toLowerCase()}`}
                  >
                    {classification.data.confidence_band} ·{' '}
                    {Math.round(
                      classification.data.recommendation.confidence * 100,
                    )}
                    %
                  </span>
                )}
              </div>
              {classification.isPending && (
                <p className="ticket-state">Loading AI insight…</p>
              )}
              {(classification.error || classify.error) && (
                <p className="ticket-error" role="alert">
                  {errorMessage(classification.error ?? classify.error)}
                </p>
              )}
              {classification.data?.status === 'FALLBACK' && (
                <p className="ai-caution">
                  Safe fallback shown ({classification.data.fallback_reason}).
                  Human review is required.
                </p>
              )}
              {classification.data && (
                <>
                  <dl className="side-facts">
                    <div>
                      <dt>Category</dt>
                      <dd>
                        {classification.data.recommendation.category ??
                          'Uncertain'}
                      </dd>
                    </div>
                    <div>
                      <dt>Subcategory</dt>
                      <dd>
                        {classification.data.recommendation.subcategory ??
                          'Uncertain'}
                      </dd>
                    </div>
                    <div>
                      <dt>Suggested priority</dt>
                      <dd>
                        {
                          classification.data.recommendation
                            .priority_recommendation
                        }
                      </dd>
                    </div>
                  </dl>
                  {classification.data.recommendation.possible_causes.length >
                    0 && (
                    <div>
                      <h3>Possible causes</h3>
                      <ul>
                        {classification.data.recommendation.possible_causes.map(
                          (cause) => (
                            <li key={cause}>{cause}</li>
                          ),
                        )}
                      </ul>
                    </div>
                  )}
                  <div>
                    <h3>Recommended checks</h3>
                    <ol>
                      {classification.data.recommendation.recommended_checks.map(
                        (check) => (
                          <li key={check}>{check}</li>
                        ),
                      )}
                    </ol>
                  </div>
                  <small>
                    Advisory only · {classification.data.provider} /{' '}
                    {classification.data.model}
                  </small>
                </>
              )}
              {!classification.isPending && classification.data === null && (
                <p className="ticket-state">
                  No classification has been generated.
                </p>
              )}
              <button
                type="button"
                onClick={() => classify.mutate()}
                disabled={classify.isPending}
              >
                {classify.isPending
                  ? 'Classifying…'
                  : classification.data
                    ? 'Regenerate classification'
                    : 'Generate classification'}
              </button>
            </section>
          )}
          {canUseAI && (
            <section
              className="ticket-panel ai-insights"
              aria-labelledby="troubleshooting-heading"
            >
              <div className="panel-heading">
                <h2 id="troubleshooting-heading">Knowledge troubleshooting</h2>
                {troubleshooting.data && (
                  <span
                    className={`confidence-${troubleshooting.data.confidence_band.toLowerCase()}`}
                  >
                    {troubleshooting.data.confidence_band} ·{' '}
                    {Math.round(
                      troubleshooting.data.recommendation.confidence * 100,
                    )}
                    %
                  </span>
                )}
              </div>
              {troubleshooting.isPending && (
                <p className="ticket-state">Loading grounded guidance…</p>
              )}
              {(troubleshooting.error || troubleshoot.error) && (
                <p className="ticket-error" role="alert">
                  {errorMessage(troubleshooting.error ?? troubleshoot.error)}
                </p>
              )}
              {troubleshooting.data?.status === 'FALLBACK' && (
                <p className="ai-caution">
                  Safe fallback shown ({troubleshooting.data.fallback_reason}).
                  Human review is required.
                </p>
              )}
              {troubleshooting.data && (
                <>
                  <p>{troubleshooting.data.recommendation.summary}</p>
                  {troubleshooting.data.recommendation.possible_causes.length >
                    0 && (
                    <div>
                      <h3>Possible causes</h3>
                      <ul>
                        {troubleshooting.data.recommendation.possible_causes.map(
                          (cause) => (
                            <li key={cause}>{cause}</li>
                          ),
                        )}
                      </ul>
                    </div>
                  )}
                  <div>
                    <h3>Recommended actions</h3>
                    <ol>
                      {troubleshooting.data.recommendation.recommended_actions.map(
                        (action) => (
                          <li key={action}>{action}</li>
                        ),
                      )}
                    </ol>
                  </div>
                  {troubleshooting.data.citations.length > 0 && (
                    <div>
                      <h3>Knowledge citations</h3>
                      <ul className="citation-list">
                        {troubleshooting.data.citations.map((citation) => (
                          <li key={citation.chunk_id}>
                            <Link to={`/knowledge/${citation.article_id}`}>
                              {citation.article_title} · v
                              {citation.article_version} · section{' '}
                              {citation.chunk_ordinal + 1}
                            </Link>
                            <p>{citation.excerpt}</p>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  <small>
                    Advisory only · retrieved published knowledge ·{' '}
                    {troubleshooting.data.provider} /{' '}
                    {troubleshooting.data.model}
                  </small>
                </>
              )}
              {!troubleshooting.isPending && troubleshooting.data === null && (
                <p className="ticket-state">
                  No grounded guidance has been generated.
                </p>
              )}
              <button
                type="button"
                onClick={() => troubleshoot.mutate()}
                disabled={troubleshoot.isPending}
              >
                {troubleshoot.isPending
                  ? 'Retrieving knowledge…'
                  : troubleshooting.data
                    ? 'Regenerate grounded guidance'
                    : 'Generate grounded guidance'}
              </button>
            </section>
          )}
          {canUseAI && (
            <section
              className="ticket-panel ai-assistant"
              aria-labelledby="assistant-heading"
            >
              <div className="panel-heading">
                <h2 id="assistant-heading">AI technician assistant</h2>
                <span>Human approval required</span>
              </div>
              <p className="ai-caution">
                Generated text is advisory. Approval only fills the reply
                composer; it never posts or changes the ticket automatically.
              </p>
              {(responseDraft.error ||
                ticketSummary.error ||
                generateDraft.error ||
                generateSummary.error ||
                reviewRecommendation.error) && (
                <p className="ticket-error" role="alert">
                  {errorMessage(
                    responseDraft.error ??
                      ticketSummary.error ??
                      generateDraft.error ??
                      generateSummary.error ??
                      reviewRecommendation.error,
                  )}
                </p>
              )}

              <div className="assistant-output">
                <div className="panel-heading">
                  <h3>Response draft</h3>
                  {draftResult && (
                    <span
                      className={`confidence-${draftResult.confidence_band.toLowerCase()}`}
                    >
                      {draftResult.confidence_band} ·{' '}
                      {Math.round(draftResult.recommendation.confidence * 100)}%
                    </span>
                  )}
                </div>
                {responseDraft.isPending && (
                  <p className="ticket-state">Loading latest response draft…</p>
                )}
                {draftResult && (
                  <>
                    {draftResult.status === 'FALLBACK' ? (
                      <p className="ai-caution">
                        Draft unavailable ({draftResult.fallback_reason}).
                      </p>
                    ) : (
                      <label>
                        Review and edit before approval
                        <textarea
                          rows={5}
                          maxLength={4000}
                          value={editedDraft}
                          onChange={(event) =>
                            setDraftEdit({
                              recommendationId: draftResult.recommendation_id,
                              value: event.target.value,
                            })
                          }
                        />
                      </label>
                    )}
                    {draftResult.recommendation.safety_notes.length > 0 && (
                      <ul>
                        {draftResult.recommendation.safety_notes.map((note) => (
                          <li key={note}>{note}</li>
                        ))}
                      </ul>
                    )}
                    {draftResult.feedback && (
                      <p className="ticket-success">
                        Review recorded: {draftResult.feedback.action}
                      </p>
                    )}
                    {draftResult.status === 'SUCCEEDED' &&
                      !draftResult.feedback && (
                        <div className="assistant-review-actions">
                          <button
                            type="button"
                            disabled={reviewRecommendation.isPending}
                            onClick={() =>
                              reviewRecommendation.mutate({
                                result: draftResult,
                                action: 'ACCEPTED',
                              })
                            }
                          >
                            Approve draft
                          </button>
                          <button
                            type="button"
                            disabled={
                              reviewRecommendation.isPending ||
                              editedDraft.trim().length < 2
                            }
                            onClick={() =>
                              reviewRecommendation.mutate({
                                result: draftResult,
                                action: 'EDITED',
                                editedContent: editedDraft.trim(),
                              })
                            }
                          >
                            Approve edited draft
                          </button>
                          <button
                            type="button"
                            disabled={reviewRecommendation.isPending}
                            onClick={() =>
                              reviewRecommendation.mutate({
                                result: draftResult,
                                action: 'REJECTED',
                              })
                            }
                          >
                            Reject
                          </button>
                        </div>
                      )}
                  </>
                )}
                <button
                  type="button"
                  disabled={generateDraft.isPending}
                  onClick={() => generateDraft.mutate()}
                >
                  {generateDraft.isPending
                    ? 'Drafting…'
                    : draftResult
                      ? 'Regenerate response draft'
                      : 'Draft response'}
                </button>
              </div>

              <div className="assistant-output">
                <div className="panel-heading">
                  <h3>Ticket summary</h3>
                  {summaryResult && (
                    <span
                      className={`confidence-${summaryResult.confidence_band.toLowerCase()}`}
                    >
                      {summaryResult.confidence_band} ·{' '}
                      {Math.round(
                        summaryResult.recommendation.confidence * 100,
                      )}
                      %
                    </span>
                  )}
                </div>
                {ticketSummary.isPending && (
                  <p className="ticket-state">Loading latest summary…</p>
                )}
                {summaryResult && (
                  <>
                    <p>{summaryResult.recommendation.summary}</p>
                    {summaryResult.recommendation.key_facts.length > 0 && (
                      <div>
                        <h4>Key facts</h4>
                        <ul>
                          {summaryResult.recommendation.key_facts.map(
                            (fact) => (
                              <li key={fact}>{fact}</li>
                            ),
                          )}
                        </ul>
                      </div>
                    )}
                    <p>
                      <strong>Suggested next step:</strong>{' '}
                      {summaryResult.recommendation.suggested_next_step}
                    </p>
                    {summaryResult.feedback && (
                      <p className="ticket-success">
                        Review recorded: {summaryResult.feedback.action}
                      </p>
                    )}
                    {summaryResult.status === 'SUCCEEDED' &&
                      !summaryResult.feedback && (
                        <div className="assistant-review-actions">
                          <button
                            type="button"
                            disabled={reviewRecommendation.isPending}
                            onClick={() =>
                              reviewRecommendation.mutate({
                                result: summaryResult,
                                action: 'ACCEPTED',
                              })
                            }
                          >
                            Accept summary
                          </button>
                          <button
                            type="button"
                            disabled={reviewRecommendation.isPending}
                            onClick={() =>
                              reviewRecommendation.mutate({
                                result: summaryResult,
                                action: 'REJECTED',
                              })
                            }
                          >
                            Reject
                          </button>
                        </div>
                      )}
                  </>
                )}
                <button
                  type="button"
                  disabled={generateSummary.isPending}
                  onClick={() => generateSummary.mutate()}
                >
                  {generateSummary.isPending
                    ? 'Summarizing…'
                    : summaryResult
                      ? 'Regenerate summary'
                      : 'Summarize ticket'}
                </button>
              </div>

              {((draftResult?.status === 'SUCCEEDED' &&
                !draftResult.feedback) ||
                (summaryResult?.status === 'SUCCEEDED' &&
                  !summaryResult.feedback)) && (
                <label>
                  Optional review note
                  <input
                    value={feedbackNote}
                    maxLength={1000}
                    onChange={(event) => setFeedbackNote(event.target.value)}
                  />
                </label>
              )}
            </section>
          )}
          {canUseAI && (
            <section
              className="ticket-panel similar-tickets"
              aria-labelledby="similar-heading"
            >
              <div className="panel-heading">
                <h2 id="similar-heading">Similar resolved tickets</h2>
                {similarTickets.data && (
                  <span>{similarTickets.data.items.length} matches</span>
                )}
              </div>
              {similarTickets.isPending && (
                <p className="ticket-state">Comparing historical tickets…</p>
              )}
              {similarTickets.error && (
                <p className="ticket-error" role="alert">
                  {errorMessage(similarTickets.error)}
                </p>
              )}
              {similarTickets.data?.items.length === 0 && (
                <p className="ticket-state">
                  No similar resolved tickets found.
                </p>
              )}
              <ol className="similar-ticket-list">
                {similarTickets.data?.items.map((match) => (
                  <li key={match.ticket_id}>
                    <div>
                      <Link to={`/tickets/${match.ticket_id}`}>
                        {match.reference} · {match.title}
                      </Link>
                      <strong>
                        {Math.round(match.similarity * 100)}% similar
                      </strong>
                    </div>
                    <p>{match.resolution_summary}</p>
                    <small>
                      {match.status} · {match.priority} priority
                      {match.category ? ` · ${match.category}` : ''}
                      {match.resolved_at
                        ? ` · resolved ${displayDate(match.resolved_at)}`
                        : ''}
                    </small>
                  </li>
                ))}
              </ol>
              <p className="ai-caution">
                Semantic similarity is supporting evidence, not an exact
                diagnosis.
              </p>
              {similarTickets.data && (
                <small>
                  {similarTickets.data.provider} / {similarTickets.data.model} ·{' '}
                  {similarTickets.data.indexed_embeddings} indexed ·{' '}
                  {similarTickets.data.reused_embeddings} reused
                </small>
              )}
              <button
                type="button"
                onClick={() => void similarTickets.refetch()}
                disabled={similarTickets.isFetching}
              >
                {similarTickets.isFetching
                  ? 'Refreshing matches…'
                  : 'Refresh matches'}
              </button>
            </section>
          )}
          <section
            className="ticket-panel sla-panel"
            aria-labelledby="sla-heading"
          >
            <div className="panel-heading">
              <h2 id="sla-heading">Service level</h2>
              {sla.data && (
                <span className="sla-badge">
                  {sla.data.state.replaceAll('_', ' ')}
                </span>
              )}
            </div>
            {sla.isPending && <p className="ticket-state">Calculating SLA…</p>}
            {sla.error && (
              <p className="ticket-error" role="alert">
                {errorMessage(sla.error)}
              </p>
            )}
            {sla.data === null && (
              <p className="ticket-state">No SLA policy applied.</p>
            )}
            {sla.data && (
              <>
                <strong>{sla.data.policy_name}</strong>
                <p>
                  {sla.data.active_target.toLowerCase()} target ·{' '}
                  {displayDuration(sla.data.remaining_seconds)} remaining
                </p>
                <progress value={sla.data.percentage} max={100}>
                  {sla.data.percentage}%
                </progress>
                <small>
                  {sla.data.percentage.toFixed(1)}% used ·{' '}
                  {displayDuration(sla.data.elapsed_seconds)} elapsed ·{' '}
                  {sla.data.calendar_name} ({sla.data.calendar_timezone})
                </small>
                {(sla.data.response_breached_at ||
                  sla.data.resolution_breached_at) && (
                  <p className="ticket-error">SLA breach recorded.</p>
                )}
              </>
            )}
          </section>

          <section className="ticket-panel">
            <h2>Requester</h2>
            <strong>{current.requester.display_name}</strong>
            <a href={`mailto:${current.requester.email}`}>
              {current.requester.email}
            </a>
            <dl className="side-facts">
              <div>
                <dt>Department</dt>
                <dd>{current.department?.name ?? 'Not assigned'}</dd>
              </div>
              <div>
                <dt>Location</dt>
                <dd>{current.location?.name ?? 'Not assigned'}</dd>
              </div>
              <div>
                <dt>First response</dt>
                <dd>{displayDate(current.first_response_at)}</dd>
              </div>
            </dl>
          </section>

          <section className="ticket-panel">
            <h2>Assignment</h2>
            <p>
              {current.assigned_technician?.display_name ??
                current.assignment_team?.name ??
                'Unassigned queue'}
            </p>
            {canAssign && teams.data && (
              <form className="side-form" onSubmit={submitAssignment}>
                <label>
                  Team
                  <select
                    name="team_id"
                    required
                    value={selectedTeam}
                    onChange={(event) => setSelectedTeam(event.target.value)}
                  >
                    <option value="">Select team</option>
                    {teams.data
                      .filter((team) => team.status === 'ACTIVE')
                      .map((team) => (
                        <option key={team.id} value={team.id}>
                          {team.name}
                        </option>
                      ))}
                  </select>
                </label>
                <label>
                  Technician
                  <select name="technician_id" defaultValue="">
                    <option value="">Team queue</option>
                    {teamDetail.data?.members.map((member) => (
                      <option key={member.user_id} value={member.user_id}>
                        {member.display_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Reason
                  <input name="reason" minLength={3} maxLength={500} required />
                </label>
                <button
                  type="submit"
                  disabled={assign.isPending || !selectedTeam}
                >
                  {assign.isPending ? 'Assigning…' : 'Update assignment'}
                </button>
              </form>
            )}
          </section>

          {nextStatuses.length > 0 && (
            <section className="ticket-panel">
              <h2>Workflow</h2>
              <form className="side-form" onSubmit={submitTransition}>
                <label>
                  Next status
                  <select name="status" required>
                    {nextStatuses.map((value) => (
                      <option key={value}>{value}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Reason
                  <input name="reason" minLength={3} maxLength={500} required />
                </label>
                {nextStatuses.includes('RESOLVED') && (
                  <>
                    <label>
                      Resolution summary
                      <textarea name="resolution_summary" rows={3} />
                    </label>
                    <label>
                      Resolution code
                      <input name="resolution_code" maxLength={64} />
                    </label>
                  </>
                )}
                <button type="submit" disabled={transition.isPending}>
                  {transition.isPending ? 'Updating…' : 'Apply transition'}
                </button>
              </form>
            </section>
          )}

          <section className="ticket-panel">
            <h2>Resolution</h2>
            {current.resolution_summary ? (
              <>
                <p>{current.resolution_summary}</p>
                <small>
                  {current.resolution_code} · {displayDate(current.resolved_at)}
                </small>
              </>
            ) : (
              <p className="ticket-state">No resolution recorded.</p>
            )}
          </section>

          <section className="ticket-panel timeline">
            <div className="panel-heading">
              <h2>Timeline</h2>
              <span>{events.data?.total ?? 0} events</span>
            </div>
            {events.isPending && (
              <p className="ticket-state">Loading timeline…</p>
            )}
            {events.error && (
              <p className="ticket-error" role="alert">
                {errorMessage(events.error)}
              </p>
            )}
            <ol>
              {events.data?.items.map((event) => (
                <li key={event.id}>
                  <strong>{event.event_type.replaceAll('.', ' ')}</strong>
                  <span>{event.reason}</span>
                  <small>
                    {event.actor.display_name} · {displayDate(event.created_at)}
                  </small>
                </li>
              ))}
            </ol>
          </section>
        </aside>
      </div>
    </main>
  )
}
