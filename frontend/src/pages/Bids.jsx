import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion, useReducedMotion } from 'framer-motion'
import { ChevronRight, FileText, FileX2, Loader2, Search } from 'lucide-react'
import { getBids } from '../api/client'
import Nav from '../components/Nav'
import Container from '../components/Container'
import Footer from '../components/Footer'

const STATUS_META = {
  published: { label: 'Open', className: 'border-success-line bg-success-soft text-success' },
  closed: { label: 'Closed', className: 'border-line bg-surface text-subtle' },
  evaluated: { label: 'Evaluated', className: 'border-line bg-surface text-subtle' },
}

function StatusChip({ status }) {
  const meta = STATUS_META[status] ?? STATUS_META.published
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${meta.className}`}>
      {meta.label}
    </span>
  )
}

function formatDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export default function Bids() {
  const reduceMotion = useReducedMotion()
  const [bids, setBids] = useState(null)
  const [error, setError] = useState('')
  const [keyword, setKeyword] = useState('')
  const [category, setCategory] = useState('')
  const [status, setStatus] = useState('')

  useEffect(() => {
    const timer = setTimeout(() => {
      getBids({ keyword: keyword || undefined, category: category || undefined, status: status || undefined })
        .then(setBids)
        .catch(() => setError('Could not load bids. Is the backend running?'))
    }, 300) // debounce keyword typing
    return () => clearTimeout(timer)
  }, [keyword, category, status])

  return (
    <div className="flex min-h-screen flex-col bg-canvas text-ink">
      <Nav />

      <Container className="flex-1">
        <main className="py-10">
          <h1 className="text-2xl font-semibold text-ink">Published Bids</h1>
          <p className="mt-1 text-sm text-subtle">Browse open tenders — no account needed to look.</p>

          <div className="mt-6 flex flex-wrap items-center gap-3 rounded-card border border-line bg-elevated p-3">
            <div className="relative min-w-[220px] flex-1">
              <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-subtle" />
              <input
                type="text"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder="Search by title or GeM bid number..."
                className="w-full rounded-md border border-line bg-canvas py-2 pl-9 pr-3 text-sm text-ink transition-colors duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
              />
            </div>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
            >
              <option value="">All categories</option>
              <option value="Electronics">Electronics</option>
            </select>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
            >
              <option value="">All statuses</option>
              <option value="published">Open</option>
              <option value="closed">Closed</option>
              <option value="evaluated">Evaluated</option>
            </select>
          </div>

          <div className="mt-6">
            {error && (
              <p className="rounded-md border border-danger-line bg-danger-soft px-4 py-3 text-sm text-danger">
                {error}
              </p>
            )}

            {!error && bids === null && (
              <div className="flex items-center gap-2 text-sm text-subtle">
                <Loader2 size={16} className="animate-spin" />
                Loading...
              </div>
            )}

            {bids?.length === 0 && (
              <div className="flex flex-col items-center gap-2 rounded-card border border-line bg-elevated px-4 py-16 text-center">
                <FileX2 size={28} className="text-subtle/50" />
                <p className="text-sm font-medium text-ink">No bids match right now</p>
                <p className="text-xs text-subtle">Try a different keyword, category, or status filter.</p>
              </div>
            )}

            {bids?.length > 0 && (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {bids.map((bid, i) => (
                  <motion.div
                    key={bid.rfp_id}
                    initial={reduceMotion ? undefined : { opacity: 0, y: 12 }}
                    animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
                    transition={{ duration: 0.3, delay: reduceMotion ? 0 : Math.min(i, 8) * 0.04, ease: 'easeOut' }}
                  >
                    <Link
                      to={`/bids/${bid.rfp_id}`}
                      className="flex h-full flex-col rounded-card border border-line bg-elevated p-5 transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-md"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent">
                          <FileText size={16} />
                        </span>
                        <StatusChip status={bid.status} />
                      </div>
                      <p className="mt-3 line-clamp-2 text-sm font-medium text-ink">{bid.title}</p>
                      <p className="mt-1 text-xs text-subtle">{bid.buyer_org}</p>
                      <div className="mt-auto flex items-center justify-between pt-4 text-xs text-subtle">
                        <span>{bid.category} &middot; closes {formatDate(bid.closing_date)}</span>
                        <ChevronRight size={14} className="shrink-0" />
                      </div>
                      {bid.gem_bid_number && (
                        <p className="mt-1 font-mono text-[11px] text-subtle/70">{bid.gem_bid_number}</p>
                      )}
                    </Link>
                  </motion.div>
                ))}
              </div>
            )}
          </div>
        </main>
      </Container>

      <Footer />
    </div>
  )
}
