import { createContext, useContext, useEffect, useState } from 'react'
import {
  getMe,
  login as loginRequest,
  signupBidder as signupBidderRequest,
  TOKEN_KEY,
} from '../api/client'

const AuthContext = createContext(null)
const ROLE_KEY = 'rfp_sentinel_role'

// BuyerDashboard.jsx's own in-flight-evaluation tracker -- lives in
// localStorage, which is per-browser, not per-account. Without clearing it
// here, switching buyer accounts in the same browser (logout, then log in
// as someone else) left the PREVIOUS account's last "RFP published
// successfully" card showing on the new account's dashboard -- stale
// client-side state, not a real server response (the server-side
// ownership check on the actual RFP data was already correct; this key
// just wasn't part of the session boundary at all). Cleared both at
// logout and at the start of a fresh session, so it can never survive
// into a different account's session either way.
const ACTIVE_EVALUATION_KEY = 'rfp_sentinel_active_evaluation'

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
    localStorage.removeItem(ACTIVE_EVALUATION_KEY)
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
    localStorage.removeItem(ACTIVE_EVALUATION_KEY)
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
