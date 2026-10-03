import { createContext, useContext } from 'react'
import type { AuthUser } from './authApi'

export type AuthState = {
  user: AuthUser | null
  accessToken: string | null
  loading: boolean
  refresh?: () => Promise<void>
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}
export const AuthContext = createContext<AuthState | null>(null)
export function useAuth(): AuthState {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used within AuthProvider')
  return value
}
