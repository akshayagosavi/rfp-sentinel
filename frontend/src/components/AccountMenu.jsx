import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ChevronDown, UserCircle2 } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

const DASHBOARD_PATH = { buyer: '/buyer/dashboard', bidder: '/bidder/dashboard', admin: '/admin/dashboard' }

// Shown instead of LoginMenu whenever a session exists -- the bug this
// fixes: the navbar used to always render the Login dropdown regardless
// of auth state, so a logged-in user still saw "Login" with nothing
// reflecting who they were signed in as.
export default function AccountMenu() {
  const { role, user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    function onClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  function handleLogout() {
    setOpen(false)
    logout()
    navigate('/')
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-full border border-line bg-elevated px-3 py-1.5 text-sm font-medium text-ink transition-colors duration-200 hover:border-accent/40"
      >
        <UserCircle2 size={16} className="text-accent" />
        {user?.org_name ?? '...'}
        <ChevronDown size={14} className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-48 overflow-hidden rounded-md border border-line bg-elevated shadow-lg">
          <div className="border-b border-line px-4 py-2.5">
            <p className="truncate text-xs text-subtle">{user?.email}</p>
            <p className="text-xs capitalize text-subtle">{role} account</p>
          </div>
          <Link
            to={DASHBOARD_PATH[role] ?? '/'}
            onClick={() => setOpen(false)}
            className="block px-4 py-2.5 text-sm text-ink transition-colors duration-200 hover:bg-surface"
          >
            Dashboard
          </Link>
          {role === 'buyer' && (
            <Link
              to="/buyer/rfps"
              onClick={() => setOpen(false)}
              className="block px-4 py-2.5 text-sm text-ink transition-colors duration-200 hover:bg-surface"
            >
              My RFPs
            </Link>
          )}
          <Link
            to="/profile"
            onClick={() => setOpen(false)}
            className="block px-4 py-2.5 text-sm text-ink transition-colors duration-200 hover:bg-surface"
          >
            Profile
          </Link>
          <button
            onClick={handleLogout}
            className="block w-full px-4 py-2.5 text-left text-sm text-danger transition-colors duration-200 hover:bg-surface"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}
