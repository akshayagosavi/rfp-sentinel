import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, FileText, Loader2 } from 'lucide-react'
import { getMyRfps } from '../api/client'
import Nav from '../components/Nav'

const STATUS_META = {
  draft: { label: 'Draft', className: 'border-line bg-surface text-subtle' },
  published: { label: 'Open', className: 'border-success-line bg-success-soft text-success' },
  closed: { label: 'Closed', className: 'border-accent/30 bg-accent/10 text-accent' },
  evaluated: { label: 'Evaluated', className: 'border-line bg-surface text-subtle' },
}

function StatusChip({ status }) {
  const meta = STATUS_META[status] ?? STATUS_META.draft
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${meta.className}`}>
      {meta.label}
    </span>
  )
}

function formatDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export default function BuyerRfps() {
  const [rfps, setRfps] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getMyRfps()
      .then(setRfps)
      .catch(() => setError('Could not load your RFPs. Is the backend running?'))
  }, [])

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <Nav />

      <div className="mx-auto max-w-3xl px-6">
        <main className="py-10">
          <h1 className="text-2xl font-semibold text-ink">My RFPs</h1>
          <p className="mt-1 text-sm text-subtle">Everything you&apos;ve published, plus its bids and status.</p>

          <div className="mt-6">
            {error && (
              <p className="rounded-md border border-danger-line bg-danger-soft px-4 py-3 text-sm text-danger">
                {error}
              </p>
            )}

            {!error && rfps === null && (
              <div className="flex items-center gap-2 text-sm text-subtle">
                <Loader2 size={16} className="animate-spin" />
                Loading...
              </div>
            )}

            {rfps?.length === 0 && (
              <p className="rounded-md border border-line bg-elevated px-4 py-6 text-center text-sm text-subtle">
                You haven&apos;t published any RFPs yet.
              </p>
            )}

            {rfps?.length > 0 && (
              <ul className="space-y-3">
                {rfps.map((rfp) => (
                  <li key={rfp.rfp_id}>
                    <Link
                      to={`/buyer/rfp/${rfp.rfp_id}`}
                      className="flex items-center justify-between rounded-card border border-line bg-elevated px-5 py-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-md"
                    >
                      <div className="flex items-start gap-3">
                        <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent">
                          <FileText size={16} />
                        </span>
                        <div>
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-medium text-ink">{rfp.title}</p>
                            <StatusChip status={rfp.status} />
                          </div>
                          <p className="mt-1 text-xs text-subtle">
                            {rfp.bid_count} bid{rfp.bid_count === 1 ? '' : 's'} &middot;{' '}
                            {rfp.status === 'published' ? `closes ${formatDate(rfp.closing_date)}` : rfp.closed_at ? `closed ${formatDate(rfp.closed_at)}` : ''}
                          </p>
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
