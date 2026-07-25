import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, useReducedMotion } from 'framer-motion'
import { ShieldCheck } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import Nav from '../components/Nav'
import GradientBackdrop from '../components/GradientBackdrop'

export default function AdminLogin() {
  const { login, logout } = useAuth()
  const navigate = useNavigate()
  const reduceMotion = useReducedMotion()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const userRole = await login(email, password)
      // The backend only checks email+password, not which login page was
      // used -- a buyer/bidder's correct credentials would otherwise
      // "succeed" here too, just to get silently redirected away later by
      // the dashboard's own role guard. Reject it right here instead, with
      // a real error, and roll back the session login() just applied.
      if (userRole !== 'admin') {
        logout()
        setError('This account is not an admin account. Use the login page for your account type.')
        return
      }
      navigate('/admin/dashboard')
    } catch {
      setError('Invalid email or password.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <GradientBackdrop />
      <Nav />

      <div className="flex min-h-[calc(100vh-73px)] items-center justify-center px-6">
        <motion.div
          initial={reduceMotion ? undefined : { opacity: 0, y: 16 }}
          animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
          className="w-full max-w-sm rounded-card border border-line bg-elevated/80 p-8 shadow-lg backdrop-blur-sm"
        >
          <div className="flex flex-col items-center text-center">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-accent/10 text-accent">
              <ShieldCheck size={20} />
            </span>
            <h1 className="mt-4 text-xl font-semibold text-ink">Admin Login</h1>
            <p className="mt-1 text-sm text-subtle">Sign in to manage the norm knowledge base.</p>
          </div>

          <form onSubmit={handleSubmit} className="mt-8 space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-ink">
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink transition-colors duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
              />
            </div>
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-ink">
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink transition-colors duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
              />
            </div>

            {error && (
              <p className="rounded-md border border-danger-line bg-danger-soft px-3 py-2 text-sm text-danger">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition-all duration-200 hover:scale-[1.01] hover:bg-accent-hover disabled:opacity-60 disabled:hover:scale-100"
            >
              {submitting ? 'Signing in...' : 'Sign in'}
            </button>
          </form>
        </motion.div>
      </div>
    </div>
  )
}
