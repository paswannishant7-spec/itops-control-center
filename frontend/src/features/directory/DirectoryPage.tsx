import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { errorMessage } from '../../api/client'
import { useAuth } from '../auth/authContextValue'
import { directoryApi } from './directoryApi'
import { ReferencePanel } from './ReferencePanel'
import { TeamsPanel } from './TeamsPanel'
import { UsersPanel } from './UsersPanel'
import './directory.css'

export function DirectoryPage() {
  const { user, accessToken } = useAuth()
  const canSeeDepartments =
    user?.permissions.includes('department:view') ?? false
  const canSeeLocations = user?.permissions.includes('location:view') ?? false
  const departments = useQuery({
    queryKey: ['directory-departments', user?.id],
    queryFn: ({ signal }) => directoryApi.departments(accessToken, signal),
    enabled: canSeeDepartments,
    retry: false,
  })
  const locations = useQuery({
    queryKey: ['directory-locations', user?.id],
    queryFn: ({ signal }) => directoryApi.locations(accessToken, signal),
    enabled: canSeeLocations,
    retry: false,
  })
  const referenceError = departments.error ?? locations.error

  return (
    <main className="directory-page">
      <header className="topbar">
        <Link className="brand" to="/">
          ← Workspace
        </Link>
        <div className="session-actions">
          <Link to="/tickets">Tickets</Link>
          <span>{user?.display_name}</span>
        </div>
      </header>
      <div className="directory-heading">
        <p className="eyebrow">Phase 5 · Organizational directory</p>
        <h1>People and support coverage</h1>
        <p>
          Manage identities, organizational references, and the technicians
          assigned to operational teams.
        </p>
      </div>
      <nav className="section-nav" aria-label="Directory sections">
        {user?.permissions.includes('user:view') && <a href="#users">Users</a>}
        <a href="#teams">Teams</a>
        {canSeeDepartments && <a href="#departments">Departments</a>}
        {canSeeLocations && <a href="#locations">Locations</a>}
      </nav>
      {referenceError && (
        <p role="alert" className="page-alert">
          {errorMessage(referenceError)}. Team and user forms will not offer
          organizational references until this is resolved.
        </p>
      )}
      <div className="directory-layout">
        {user?.permissions.includes('user:view') && (
          <UsersPanel
            departments={departments.data ?? []}
            locations={locations.data ?? []}
          />
        )}
        <TeamsPanel
          departments={departments.data ?? []}
          locations={locations.data ?? []}
        />
        {canSeeDepartments && (
          <ReferencePanel
            kind="department"
            records={departments.data ?? []}
            canManage={user?.permissions.includes('department:manage') ?? false}
            pending={departments.isPending}
            error={departments.error}
            retry={() => void departments.refetch()}
          />
        )}
        {canSeeLocations && (
          <ReferencePanel
            kind="location"
            records={locations.data ?? []}
            canManage={user?.permissions.includes('location:manage') ?? false}
            pending={locations.isPending}
            error={locations.error}
            retry={() => void locations.refetch()}
          />
        )}
      </div>
    </main>
  )
}
