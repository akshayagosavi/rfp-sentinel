import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, FileText, Loader2, Search } from 'lucide-react'
import { getBids } from '../api/client'
import Nav from '../components/Nav'

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
    <div className="min-h-screen bg-canvas text-ink">
      <Nav />

      <div className="mx-auto max-w-4xl px-6">
        <main className="py-10">
          <h1 className="text-2xl font-semibold text-ink">Published Bids</h1>
          <p className="mt-1 text-sm text-subtle">Browse open tenders — no account needed to look.</p>

          <div className="mt-6 flex flex-wrap gap-3">
            <div className="relative flex-1 min-w-[200px]">
              <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-subtle" />
              <input
                type="text"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder="Search by title or GeM bid number..."
                className="w-full rounded-md border border-line bg-elevated py-2 pl-9 pr-3 text-sm text-ink transition-colors duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
              />
            </div>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="rounded-md border border-line bg-elevated px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
            >
              <option value="">All categories</option>
              <option value="Electronics">Electronics</option>
            </select>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="rounded-md border border-line bg-elevated px-3 py-2 text-sm text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
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
              <p className="rounded-md border border-line bg-elevated px-4 py-6 text-center text-sm text-subtle">
                No bids match right now.
              </p>
            )}

            {bids?.length > 0 && (
              <ul className="space-y-3">
                {bids.map((bid) => (
                  <li key={bid.rfp_id}>
                    <Link
                      to={`/bids/${bid.rfp_id}`}
                      className="flex items-center justify-between rounded-card border border-line bg-elevated px-5 py-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-md"
                    >
                      <div className="flex items-start gap-3">
                        <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent">
                          <FileText size={16} />
                        </span>
                        <div>
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-medium text-ink">{bid.title}</p>
                            <StatusChip status={bid.status} />
                          </div>
                          <p className="mt-1 text-xs text-subtle">
                            {bid.buyer_org} &middot; {bid.category} &middot; closes {formatDate(bid.closing_date)}
                          </p>
                          {bid.gem_bid_number && (
                            <p className="mt-0.5 font-mono text-[11px] text-subtle/70">{bid.gem_bid_number}</p>
                          )}
                        </div>
                      </div>
                      <ChevronRight size={16} className="shrink-0 text-subtle" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
