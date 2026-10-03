import '@testing-library/jest-dom/vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AuthContext } from './authContextValue'
import { ProtectedRoute } from './ProtectedRoute'

const actions = {
  accessToken: null,
  login: async () => {},
  logout: async () => {},
}

describe('ProtectedRoute', () => {
  it('denies a signed-in user who opens a forbidden URL directly', () => {
    const user = {
      id: 'a135c9eb-6ae3-467c-a4d0-6ff1ad19459c',
      email: 'employee@example.com',
      display_name: 'Employee',
      status: 'ACTIVE',
      roles: ['EMPLOYEE'],
      permissions: ['ticket:view_own'],
    }
    render(
      <AuthContext.Provider value={{ ...actions, user, loading: false }}>
        <MemoryRouter initialEntries={['/admin']}>
          <Routes>
            <Route element={<ProtectedRoute permission="role:view" />}>
              <Route path="/admin" element={<h1>Secret catalog</h1>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    )
    expect(
      screen.getByRole('heading', { name: 'Access restricted' }),
    ).toBeInTheDocument()
    expect(screen.queryByText('Secret catalog')).not.toBeInTheDocument()
  })
  it('redirects an anonymous visitor to sign in', () => {
    render(
      <AuthContext.Provider value={{ ...actions, user: null, loading: false }}>
        <MemoryRouter initialEntries={['/private']}>
          <Routes>
            <Route path="/login" element={<h1>Sign in</h1>} />
            <Route element={<ProtectedRoute />}>
              <Route path="/private" element={<h1>Private</h1>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    )
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('renders protected content for an authenticated user', () => {
    const user = {
      id: '73bb9477-5b69-4ee5-aacf-e80ed38a22520',
      email: 'operator@example.com',
      display_name: 'Operator',
      status: 'ACTIVE',
      roles: ['EMPLOYEE'],
      permissions: [],
    }
    render(
      <AuthContext.Provider value={{ ...actions, user, loading: false }}>
        <MemoryRouter initialEntries={['/private']}>
          <Routes>
            <Route element={<ProtectedRoute />}>
              <Route path="/private" element={<h1>Private</h1>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    )
    expect(screen.getByRole('heading', { name: 'Private' })).toBeInTheDocument()
  })

  it('allows the directory route only with team:view', () => {
    const user = {
      id: '35c99b4c-0c0d-4f71-a9ff-cb80df1c1063',
      email: 'manager@example.com',
      display_name: 'Manager',
      status: 'ACTIVE',
      roles: ['IT_MANAGER'],
      permissions: ['team:view'],
    }
    render(
      <AuthContext.Provider value={{ ...actions, user, loading: false }}>
        <MemoryRouter initialEntries={['/directory']}>
          <Routes>
            <Route element={<ProtectedRoute permission="team:view" />}>
              <Route path="/directory" element={<h1>Team directory</h1>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>,
    )
    expect(
      screen.getByRole('heading', { name: 'Team directory' }),
    ).toBeInTheDocument()
  })
})
