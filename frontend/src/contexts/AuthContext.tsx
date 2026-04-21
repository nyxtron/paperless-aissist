import { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import api from '../api/client'

interface AuthContextType {
  token: string | null
  isAuthEnabled: boolean
  isAuthenticated: boolean
  loading: boolean
  login: (token: string) => void
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextType>({
  token: null,
  isAuthEnabled: false,
  isAuthenticated: false,
  loading: true,
  login: () => {},
  logout: async () => {},
})

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(localStorage.getItem('paperless_token'))
  const [isAuthEnabled, setIsAuthEnabled] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .get('/auth/status')
      .then((res) => {
        setIsAuthEnabled(res.data.auth_enabled)
      })
      .catch(() => {
        // If status endpoint fails, assume auth is disabled
      })
      .finally(() => {
        setLoading(false)
      })
  }, [])

  const login = (newToken: string) => {
    localStorage.setItem('paperless_token', newToken)
    setToken(newToken)
  }

  const logout = async () => {
    try {
      await api.post('/auth/logout')
    } catch {
      // ignore
    }
    localStorage.removeItem('paperless_token')
    setToken(null)
  }

  const isAuthenticated = !isAuthEnabled || token !== null

  return (
    <AuthContext.Provider value={{ token, isAuthEnabled, isAuthenticated, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
