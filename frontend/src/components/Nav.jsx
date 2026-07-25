import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ShieldCheck } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import ThemeToggle from './ThemeToggle'
import LoginMenu from './LoginMenu'
import AccountMenu from './AccountMenu'

// Every page renders this same Nav -- the auth-aware Login/Account menu
// lives here, once, instead of every page individually computing
// `isAuthenticated ? <AccountMenu /> : <LoginMenu />` (the inconsistency
// that caused some pages, like the admin stub, to have no menu at all).
// `children` is only for page-specific EXTRA links (e.g. "Browse Bids" on
// the landing page) -- the account/login menu is automatic, never passed in.
export default function Nav({ children }) {
  const [scrolled, setScrolled] = useState(false)
  const { isAuthenticated } = useAuth()

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header
      className={`sticky top-0 z-50 border-b border-line transition-all duration-300 ${
        scrolled ? 'bg-canvas/70 backdrop-blur-md' : 'bg-transparent'
      }`}
    >
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 lg:px-8">
        <Link
          to="/"
          className="flex items-center gap-2 text-lg font-semibold tracking-tight text-ink transition-opacity duration-200 hover:opacity-80"
        >
          <ShieldCheck size={20} className="text-accent" />
          RFP Sentinel
        </Link>
        <div className="flex items-center gap-4">
          <ThemeToggle />
          {children}
          {isAuthenticated ? <AccountMenu /> : <LoginMenu />}
        </div>
      </div>
    </header>
  )
}
