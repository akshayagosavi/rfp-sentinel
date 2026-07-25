import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion, useReducedMotion } from 'framer-motion'
import { ChevronRight, FileStack, FileText, Loader2 } from 'lucide-react'
import { getMyRfps } from '../api/client'
import Nav from '../components/Nav'
import Container from '../components/Container'
import Footer from '../components/Footer'

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
  const reduceMotion = useReducedMotion()
  const [rfps, setRfps] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getMyRfps()
      .then(setRfps)
      .catch(() => setError('Could not load your RFPs. Is the backend running?'))
  }, [])

  return (
    <div className="flex min-h-screen flex-col bg-canvas text-ink">
      <Nav />

      <Container className="flex-1">
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
              <div className="flex flex-col items-center gap-2 rounded-card border border-line bg-elevated px-4 py-16 text-center">
                <FileStack size={28} className="text-subtle/50" />
                <p className="text-sm font-medium text-ink">You haven&apos;t published any RFPs yet</p>
                <Link to="/buyer/dashboard" className="text-xs font-medium text-accent hover:underline">
                  Upload your first RFP
                </Link>
              </div>
            )}

            {rfps?.length > 0 && (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {rfps.map((rfp, i) => (
                  <motion.div
                    key={rfp.rfp_id}
                    initial={reduceMotion ? undefined : { opacity: 0, y: 12 }}
                    animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
                    transition={{ duration: 0.3, delay: reduceMotion ? 0 : Math.min(i, 8) * 0.04, ease: 'easeOut' }}
                  >
                    <Link
                      to={`/buyer/rfp/${rfp.rfp_id}`}
                      className="flex h-full flex-col rounded-card border border-line bg-elevated p-5 transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-md"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent">
                          <FileText size={16} />
                        </span>
                        <StatusChip status={rfp.status} />
                      </div>
                      <p className="mt-3 line-clamp-2 text-sm font-medium text-ink">{rfp.title}</p>
                      <div className="mt-auto flex items-center justify-between pt-4 text-xs text-subtle">
                        <span>
                          {rfp.bid_count} bid{rfp.bid_count === 1 ? '' : 's'} &middot;{' '}
                          {rfp.status === 'published'
                            ? `closes ${formatDate(rfp.closing_date)}`
                            : rfp.closed_at
                              ? `closed ${formatDate(rfp.closed_at)}`
                              : ''}
                        </span>
                        <ChevronRight size={14} className="shrink-0" />
                      </div>
                    </Link>
                  </motion.div>
                ))}
              </div>
            )}
          </div>
        </main>
      </Container>

      <Footer slim />
    </div>
  )
}
