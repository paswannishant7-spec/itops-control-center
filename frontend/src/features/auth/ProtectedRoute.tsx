import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from './authContextValue'

export function ProtectedRoute({ permission }: { permission?: string }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading)
    return (
      <main className="centered-page" aria-busy="true">
        <p>Restoring your secure session…</p>
      </main>
    )
  if (!user)
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (permission && !user.permissions.includes(permission))
    return (
      <main className="centered-page">
        <section className="error-panel">
          <h1>Access restricted</h1>
          <p>Your account does not have access to this area.</p>
          <a className="button-link" href="/">
            Return home
          </a>
        </section>
      </main>
    )
  return <Outlet />
}
