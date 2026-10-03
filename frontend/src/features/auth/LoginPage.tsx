import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from './authContextValue'

export function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  if (user) return <Navigate to="/" replace />

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    const form = new FormData(event.currentTarget)
    try {
      await login(String(form.get('email')), String(form.get('password')))
      const target = (location.state as { from?: string } | null)?.from ?? '/'
      navigate(target, { replace: true })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Sign-in failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-intro">
        <a className="brand" href="/">
          <span className="brand-mark" aria-hidden="true">
            IO
          </span>
          <span>ITOps Control Center</span>
        </a>
        <p className="eyebrow">Secure operations workspace</p>
        <h1>Support the business. Protect every session.</h1>
        <p>
          Sign in with your company account to access authorized service desk
          and operations workflows.
        </p>
      </section>
      <section className="login-panel" aria-labelledby="sign-in-title">
        <div>
          <p className="eyebrow">Identity</p>
          <h2 id="sign-in-title">Sign in</h2>
          <p>
            Access tokens stay in memory. Your session is renewed through a
            protected cookie.
          </p>
        </div>
        <form onSubmit={submit}>
          <label htmlFor="email">Work email</label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="username"
            required
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            maxLength={128}
          />
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in securely'}
          </button>
        </form>
      </section>
    </main>
  )
}
