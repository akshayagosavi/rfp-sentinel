import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown } from 'lucide-react'

const ROLES = [
  { label: 'Buyer', to: '/login' },
  { label: 'Bidder', to: '/bidder/login' },
  { label: 'Admin', to: '/admin/login' },
]

// Replaces the earlier two separate "Buyer Login"/"Bidder Login" links --
// one menu, three role options, matching the target information
// architecture (login is role-selected from one place in the navbar).
export default function LoginMenu() {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    function onClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 rounded-full bg-accent px-4 py-2 text-sm font-medium text-white transition-all duration-200 hover:scale-[1.03] hover:bg-accent-hover hover:shadow-[0_0_24px_-6px_var(--color-accent)]"
      >
        Login
        <ChevronDown size={14} className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-40 overflow-hidden rounded-md border border-line bg-elevated shadow-lg">
          {ROLES.map((role) => (
            <Link
              key={role.label}
              to={role.to}
              onClick={() => setOpen(false)}
              className="block px-4 py-2.5 text-sm text-ink transition-colors duration-200 hover:bg-surface"
            >
              {role.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
