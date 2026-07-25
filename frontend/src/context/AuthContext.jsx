import { createContext, useContext, useState } from 'react'
import { login as loginRequest, TOKEN_KEY } from '../api/client'

const AuthContext = createContext(null)
const ROLE_KEY = 'rfp_sentinel_role'

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY))
  const [role, setRole] = useState(() => localStorage.getItem(ROLE_KEY))

  async function login(email, password) {
    const { accessToken, role: userRole } = await loginRequest(email, password)
    localStorage.setItem(TOKEN_KEY, accessToken)
    localStorage.setItem(ROLE_KEY, userRole)
    setToken(accessToken)
    setRole(userRole)
    return userRole
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(ROLE_KEY)
    setToken(null)
    setRole(null)
  }

  return (
    <AuthContext.Provider value={{ token, role, isAuthenticated: !!token, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
