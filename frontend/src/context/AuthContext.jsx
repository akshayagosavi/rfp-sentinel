import { createContext, useContext, useEffect, useState } from 'react'
import {
  getMe,
  login as loginRequest,
  signupBidder as signupBidderRequest,
  TOKEN_KEY,
} from '../api/client'

const AuthContext = createContext(null)
const ROLE_KEY = 'rfp_sentinel_role'

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY))
  const [role, setRole] = useState(() => localStorage.getItem(ROLE_KEY))
  const [user, setUser] = useState(null) // { email, role, org_name, gem_seller_proof, created_at }

  // Refetches on every token change (login, signup, or an existing session
  // resuming on page load) -- keeps the navbar/profile page from ever
  // showing stale org_name after an edit, and is why the "logged in but
  // navbar still says Login" bug happened: nothing previously reacted to
  // token state to know a session existed at all beyond the raw string.
  useEffect(() => {
    if (!token) {
      setUser(null)
      return
    }
    getMe()
      .then(setUser)
      .catch(() => setUser(null))
  }, [token])

  function _applySession(accessToken, userRole) {
    localStorage.setItem(TOKEN_KEY, accessToken)
    localStorage.setItem(ROLE_KEY, userRole)
    setToken(accessToken)
    setRole(userRole)
    return userRole
  }

  async function login(email, password) {
    const { accessToken, role: userRole } = await loginRequest(email, password)
    return _applySession(accessToken, userRole)
  }

  async function signupBidder(email, password, orgName, gemSellerProof) {
    const { accessToken, role: userRole } = await signupBidderRequest(email, password, orgName, gemSellerProof)
    return _applySession(accessToken, userRole)
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(ROLE_KEY)
    setToken(null)
    setRole(null)
  }

  async function refreshUser() {
    if (!token) return
    setUser(await getMe())
  }

  return (
    <AuthContext.Provider
      value={{ token, role, user, isAuthenticated: !!token, login, signupBidder, logout, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
