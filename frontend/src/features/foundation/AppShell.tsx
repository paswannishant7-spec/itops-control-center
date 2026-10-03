import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/authContextValue'
import './app-shell.css'

type NavigationItem = {
  label: string
  to: string
  permission?: string
  anyPermission?: string[]
}

const navigation: Array<{ label: string; items: NavigationItem[] }> = [
  {
    label: 'Workspace',
    items: [
      { label: 'Overview', to: '/' },
      {
        label: 'Tickets',
        to: '/tickets',
        anyPermission: [
          'ticket:create',
          'ticket:view_own',
          'ticket:view_team',
          'ticket:view_all',
        ],
      },
      { label: 'Knowledge', to: '/knowledge', permission: 'knowledge:view' },
      {
        label: 'Assets',
        to: '/assets',
        anyPermission: ['asset:view_own', 'asset:view_team', 'asset:view_all'],
      },
    ],
  },
  {
    label: 'Operations',
    items: [
      { label: 'Monitoring', to: '/monitoring', permission: 'monitoring:view' },
      { label: 'Alerts', to: '/alerts', permission: 'alert:view' },
      {
        label: 'Command center',
        to: '/analytics',
        permission: 'analytics:view',
      },
    ],
  },
  {
    label: 'Administration',
    items: [
      { label: 'People & teams', to: '/directory', permission: 'team:view' },
      {
        label: 'Access',
        to: '/administration/access',
        permission: 'role:view',
      },
      {
        label: 'SLA policies',
        to: '/administration/sla',
        permission: 'sla:view',
      },
      { label: 'Audit', to: '/administration/audit', permission: 'audit:view' },
    ],
  },
]

const pageNames: Array<[string, string]> = [
  ['/administration/access', 'Access management'],
  ['/administration/audit', 'Audit trail'],
  ['/administration/sla', 'SLA policies'],
  ['/monitoring', 'Device monitoring'],
  ['/analytics', 'Command center'],
  ['/directory', 'People & teams'],
  ['/knowledge/', 'Knowledge article'],
  ['/knowledge', 'Knowledge base'],
  ['/tickets/', 'Ticket workstation'],
  ['/tickets', 'Ticket queue'],
  ['/assets/', 'Asset details'],
  ['/assets', 'Asset inventory'],
  ['/alerts', 'Alerts'],
  ['/', 'Overview'],
]

export function AppShell() {
  const { user, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [logoutError, setLogoutError] = useState<string | null>(null)
  const permissions = useMemo(
    () => new Set(user?.permissions ?? []),
    [user?.permissions],
  )
  const role = user?.roles[0]?.replaceAll('_', ' ') ?? 'User'
  const currentPage =
    pageNames.find(([path]) =>
      path === '/'
        ? location.pathname === '/'
        : location.pathname.startsWith(path),
    )?.[1] ?? 'Workspace'

  useEffect(() => {
    window.scrollTo(0, 0)
  }, [location.pathname])

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const value = search.trim()
    void navigate(
      value ? `/tickets?search=${encodeURIComponent(value)}` : '/tickets',
    )
  }

  return (
    <div className="app-frame">
      <aside className={`app-sidebar${open ? ' is-open' : ''}`}>
        <div className="sidebar-brand">
          <span className="brand-mark" aria-hidden="true">
            IO
          </span>
          <div>
            <strong>ITOps</strong>
            <span>Control Center</span>
          </div>
          <button
            className="sidebar-close"
            type="button"
            aria-label="Close navigation"
            onClick={() => setOpen(false)}
          >
            ×
          </button>
        </div>
        <nav className="app-navigation" aria-label="Primary navigation">
          {navigation.map((group) => {
            const items = group.items.filter(
              (item) =>
                (!item.permission || permissions.has(item.permission)) &&
                (!item.anyPermission ||
                  item.anyPermission.some((permission) =>
                    permissions.has(permission),
                  )),
            )
            if (!items.length) return null
            return (
              <div className="nav-group" key={group.label}>
                <p>{group.label}</p>
                {items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === '/'}
                    onClick={() => setOpen(false)}
                    className={({ isActive }) =>
                      isActive ? 'active' : undefined
                    }
                  >
                    <span className="nav-marker" aria-hidden="true" />
                    {item.label}
                  </NavLink>
                ))}
              </div>
            )
          })}
        </nav>
        <div className="sidebar-account">
          <span className="account-avatar" aria-hidden="true">
            {user?.display_name?.slice(0, 1).toUpperCase()}
          </span>
          <div>
            <strong>{user?.display_name}</strong>
            <span>{role.toLowerCase()}</span>
          </div>
          <button
            type="button"
            onClick={() => {
              setLogoutError(null)
              void logout().catch(() => setLogoutError('Sign-out failed.'))
            }}
          >
            Sign out
          </button>
          {logoutError && <p role="alert">{logoutError}</p>}
        </div>
      </aside>
      {open && (
        <button
          className="sidebar-scrim"
          type="button"
          aria-label="Close navigation"
          onClick={() => setOpen(false)}
        />
      )}
      <div className="app-main">
        <header className="app-header">
          <button
            className="menu-button"
            type="button"
            aria-label="Open navigation"
            aria-expanded={open}
            onClick={() => setOpen(true)}
          >
            <span />
            <span />
            <span />
          </button>
          <div className="page-identity">
            <span>IT operations</span>
            <strong>{currentPage}</strong>
          </div>
          <form className="global-search" role="search" onSubmit={submitSearch}>
            <label className="sr-only" htmlFor="global-ticket-search">
              Search tickets
            </label>
            <input
              id="global-ticket-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search tickets"
            />
            <button type="submit">Search</button>
          </form>
          {permissions.has('alert:view') && (
            <NavLink className="notification-link" to="/alerts">
              Alerts
              <span aria-hidden="true" />
            </NavLink>
          )}
          <div className="header-account" aria-label="Signed-in account">
            <span className="account-avatar" aria-hidden="true">
              {user?.display_name?.slice(0, 1).toUpperCase()}
            </span>
            <div>
              <strong>{user?.display_name}</strong>
              <span>{role.toLowerCase()}</span>
            </div>
          </div>
        </header>
        <div className="app-page">
          <Outlet />
        </div>
      </div>
    </div>
  )
}
