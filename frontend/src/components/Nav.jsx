import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ShieldCheck } from 'lucide-react'
import ThemeToggle from './ThemeToggle'

export default function Nav({ children }) {
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll)
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header
      className={`sticky top-0 z-50 transition-all duration-300 ${
        scrolled
          ? 'border-b border-line bg-canvas/70 backdrop-blur-md'
          : 'border-b border-transparent bg-transparent'
      }`}
    >
      <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
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
        </div>
      </div>
    </header>
  )
}
