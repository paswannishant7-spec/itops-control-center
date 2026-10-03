import {
  type PropsWithChildren,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import {
  type AuthUser,
  loginRequest,
  logoutRequest,
  refreshRequest,
} from './authApi'
import { AuthContext, type AuthState } from './authContextValue'

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [accessToken, setAccessToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [renewAt, setRenewAt] = useState<number | null>(null)
  const generation = useRef(0)
  useEffect(() => {
    let active = true
    const version = generation.current
    refreshRequest()
      .then((result) => {
        if (!active || version !== generation.current) return
        setUser(result.user)
        setAccessToken(result.access_token)
        setRenewAt(Date.now() + (result.expires_in - 30) * 1000)
      })
      .catch(() => {
        if (!active || version !== generation.current) return
        setUser(null)
        setAccessToken(null)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])
  useEffect(() => {
    if (renewAt === null) return
    const version = generation.current
    const timer = window.setTimeout(
      () => {
        refreshRequest()
          .then((result) => {
            if (version !== generation.current) return
            setUser(result.user)
            setAccessToken(result.access_token)
            setRenewAt(Date.now() + (result.expires_in - 30) * 1000)
          })
          .catch(() => {
            if (version !== generation.current) return
            setUser(null)
            setAccessToken(null)
            setRenewAt(null)
          })
      },
      Math.max(0, renewAt - Date.now()),
    )
    return () => window.clearTimeout(timer)
  }, [renewAt])
  const value = useMemo<AuthState>(
    () => ({
      user,
      accessToken,
      loading,
      refresh: async () => {
        const version = generation.current
        try {
          const result = await refreshRequest()
          if (version !== generation.current) return
          setUser(result.user)
          setAccessToken(result.access_token)
          setRenewAt(Date.now() + (result.expires_in - 30) * 1000)
        } catch (error) {
          if (version === generation.current) {
            setUser(null)
            setAccessToken(null)
            setRenewAt(null)
          }
          throw error
        }
      },
      login: async (email, password) => {
        generation.current += 1
        const result = await loginRequest(email, password)
        setUser(result.user)
        setAccessToken(result.access_token)
        setRenewAt(Date.now() + (result.expires_in - 30) * 1000)
      },
      logout: async () => {
        await logoutRequest()
        generation.current += 1
        setUser(null)
        setAccessToken(null)
        setRenewAt(null)
      },
    }),
    [user, accessToken, loading],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
