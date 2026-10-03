import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { errorMessage } from '../../api/client'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { useAuth } from '../auth/authContextValue'
import {
  articleStatuses,
  createArticle,
  createCategory,
  getArticles,
  getCategories,
} from './knowledgeApi'
import './knowledge.css'

export function KnowledgePage() {
  const { accessToken, user } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [status, setStatus] = useState('')
  const [showAuthoring, setShowAuthoring] = useState(false)
  const debouncedSearch = useDebouncedValue(search.trim())
  const categories = useQuery({
    queryKey: ['knowledge-categories'],
    queryFn: ({ signal }) => getCategories(accessToken, signal),
  })
  const articles = useQuery({
    queryKey: ['knowledge-articles', debouncedSearch, categoryId, status],
    queryFn: ({ signal }) =>
      getArticles(
        accessToken,
        { search: debouncedSearch, categoryId, status },
        signal,
      ),
  })
  const create = useMutation({
    mutationFn: (input: Parameters<typeof createArticle>[1]) =>
      createArticle(accessToken, input),
    onSuccess: (article) => navigate(`/knowledge/${article.id}`),
  })
  const addCategory = useMutation({
    mutationFn: (input: Parameters<typeof createCategory>[1]) =>
      createCategory(accessToken, input),
    onSuccess: () =>
      void queryClient.invalidateQueries({
        queryKey: ['knowledge-categories'],
      }),
  })
  const canCreate = user?.permissions.includes('knowledge:create') ?? false
  const canPublish = user?.permissions.includes('knowledge:publish') ?? false

  function submitArticle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    create.mutate({
      slug: String(data.get('slug')),
      category_id: String(data.get('category_id')),
      title: String(data.get('title')),
      summary: String(data.get('summary')),
      content: String(data.get('content')),
      change_summary: String(data.get('change_summary')),
      tags: String(data.get('tags'))
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean),
    })
  }

  function submitCategory(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    addCategory.mutate(
      {
        code: String(data.get('code')).toUpperCase(),
        name: String(data.get('name')),
        description: String(data.get('description')) || null,
        is_active: true,
      },
      { onSuccess: () => form.reset() },
    )
  }

  return (
    <main className="knowledge-shell">
      <header className="knowledge-header">
        <div>
          <Link to="/" className="back-link">
            ← Control center
          </Link>
          <p className="eyebrow">Knowledge base</p>
          <h1>Trusted answers, under review.</h1>
          <p>
            Search published guidance or move operational knowledge through a
            controlled workflow.
          </p>
        </div>
        {canCreate && (
          <button
            type="button"
            onClick={() => setShowAuthoring((value) => !value)}
          >
            {showAuthoring ? 'Close editor' : 'Create article'}
          </button>
        )}
      </header>

      <section className="knowledge-filters" aria-label="Knowledge filters">
        <label>
          Search
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="VPN, email, access…"
          />
        </label>
        <label>
          Category
          <select
            value={categoryId}
            onChange={(event) => setCategoryId(event.target.value)}
          >
            <option value="">All categories</option>
            {categories.data
              ?.filter((item) => item.is_active)
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
          </select>
        </label>
        {canCreate && (
          <label>
            Status
            <select
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">All visible states</option>
              {articleStatuses.map((item) => (
                <option key={item}>{item.replace('_', ' ')}</option>
              ))}
            </select>
          </label>
        )}
      </section>

      {articles.isError && (
        <section className="knowledge-notice" role="alert">
          <p>{errorMessage(articles.error)}</p>
          <button onClick={() => void articles.refetch()}>Retry</button>
        </section>
      )}
      {!articles.isError &&
        !articles.isLoading &&
        articles.data?.total === 0 && (
          <section className="knowledge-notice">
            <p>
              {search || categoryId || status
                ? 'No articles match these filters.'
                : 'No knowledge articles are available yet.'}
            </p>
            {(search || categoryId || status) && (
              <button
                type="button"
                onClick={() => {
                  setSearch('')
                  setCategoryId('')
                  setStatus('')
                }}
              >
                Clear filters
              </button>
            )}
          </section>
        )}
      <section className="article-grid" aria-label="Knowledge articles">
        {articles.data?.items.map((article) => (
          <Link
            className="article-card"
            to={`/knowledge/${article.id}`}
            key={article.id}
          >
            <div>
              <span
                className={`knowledge-status status-${article.status.toLowerCase()}`}
              >
                {article.status.replace('_', ' ')}
              </span>
              <span>{article.category.name}</span>
            </div>
            <h2>{article.version.title}</h2>
            <p>{article.version.summary}</p>
            <footer>
              <span>v{article.version.version}</span>
              <span>{article.owner.display_name}</span>
            </footer>
          </Link>
        ))}
      </section>

      {showAuthoring && canCreate && (
        <section className="knowledge-workbench">
          <form onSubmit={submitArticle}>
            <h2>New article draft</h2>
            <label>
              Title
              <input name="title" minLength={3} required />
            </label>
            <label>
              Slug
              <input name="slug" pattern="[a-z0-9]+(?:-[a-z0-9]+)*" required />
            </label>
            <label>
              Category
              <select name="category_id" required>
                <option value="">Select category</option>
                {categories.data
                  ?.filter((item) => item.is_active)
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Summary
              <textarea name="summary" minLength={3} required />
            </label>
            <label>
              Content
              <textarea name="content" minLength={10} rows={10} required />
            </label>
            <label>
              Tags <small>comma separated</small>
              <input name="tags" />
            </label>
            <label>
              Change summary
              <input
                name="change_summary"
                minLength={3}
                defaultValue="Initial draft"
                required
              />
            </label>
            {create.isError && <p role="alert">{errorMessage(create.error)}</p>}
            <button disabled={create.isPending}>Save draft</button>
          </form>
          {canPublish && (
            <form onSubmit={submitCategory}>
              <h2>Add category</h2>
              <label>
                Code
                <input name="code" pattern="[A-Za-z0-9_]+" required />
              </label>
              <label>
                Name
                <input name="name" required />
              </label>
              <label>
                Description
                <textarea name="description" />
              </label>
              {addCategory.isError && (
                <p role="alert">{errorMessage(addCategory.error)}</p>
              )}
              <button disabled={addCategory.isPending}>Create category</button>
            </form>
          )}
        </section>
      )}
    </main>
  )
}
