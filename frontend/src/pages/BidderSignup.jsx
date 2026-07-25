import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion, useReducedMotion } from 'framer-motion'
import { Handshake } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import Nav from '../components/Nav'
import GradientBackdrop from '../components/GradientBackdrop'

export default function BidderSignup() {
  const { signupBidder } = useAuth()
  const navigate = useNavigate()
  const reduceMotion = useReducedMotion()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [orgName, setOrgName] = useState('')
  const [gemSellerProof, setGemSellerProof] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await signupBidder(email, password, orgName, gemSellerProof)
      navigate('/bidder/dashboard')
    } catch (err) {
      setError(err.response?.status === 409 ? 'An account with this email already exists.' : 'Signup failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <GradientBackdrop />
      <Nav />

      <div className="flex min-h-[calc(100vh-73px)] items-center justify-center px-6 py-10">
        <motion.div
          initial={reduceMotion ? undefined : { opacity: 0, y: 16 }}
          animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
          className="w-full max-w-sm rounded-card border border-line bg-elevated/80 p-8 shadow-lg backdrop-blur-sm"
        >
          <div className="flex flex-col items-center text-center">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-accent/10 text-accent">
              <Handshake size={20} />
            </span>
            <h1 className="mt-4 text-xl font-semibold text-ink">Seller Signup</h1>
            <p className="mt-1 text-sm text-subtle">Create an account to view and bid on published RFPs.</p>
          </div>

          <form onSubmit={handleSubmit} className="mt-8 space-y-4">
            <div>
              <label htmlFor="orgName" className="block text-sm font-medium text-ink">
                Company / seller name
              </label>
              <input
                id="orgName"
                type="text"
                required
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                className="mt-1 w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink transition-colors duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
              />
            </div>
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
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink transition-colors duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
              />
            </div>
            <div>
              <label htmlFor="gemSellerProof" className="block text-sm font-medium text-ink">
                GeM Seller ID <span className="font-normal text-subtle">(optional, for now)</span>
              </label>
              <input
                id="gemSellerProof"
                type="text"
                placeholder="e.g. your GeM seller registration number"
                value={gemSellerProof}
                onChange={(e) => setGemSellerProof(e.target.value)}
                className="mt-1 w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink transition-colors duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
              />
              <p className="mt-1 text-xs text-subtle">
                Not verified yet -- stored for when this integrates with real GeM seller records.
              </p>
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
              {submitting ? 'Creating account...' : 'Sign up'}
            </button>
          </form>

          <p className="mt-6 text-center text-xs text-subtle">
            Already have an account?{' '}
            <Link to="/bidder/login" className="font-medium text-accent hover:underline">
              Sign in
            </Link>
          </p>
        </motion.div>
      </div>
    </div>
  )
}
