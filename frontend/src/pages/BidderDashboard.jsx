import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion, useReducedMotion } from 'framer-motion'
import { CheckCircle2, ChevronRight, Clock, FileStack, FileText, Loader2, XCircle } from 'lucide-react'
import { getMyBids } from '../api/client'
import Nav from '../components/Nav'
import Container from '../components/Container'
import Footer from '../components/Footer'
import { KpiCard, KpiStrip } from '../components/KpiStrip'

const STATUS_META = {
  submitted: { label: 'Submitted', className: 'border-accent/30 bg-accent/10 text-accent' },
  under_evaluation: { label: 'Under evaluation', className: 'border-accent/30 bg-accent/10 text-accent' },
  stage1_passed: { label: 'Passed', className: 'border-success-line bg-success-soft text-success' },
  stage1_failed: { label: 'Not selected', className: 'border-danger-line bg-danger-soft text-danger' },
}

function StatusChip({ status }) {
  const meta = STATUS_META[status] ?? STATUS_META.submitted
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${meta.className}`}>
      {meta.label}
    </span>
  )
}

export default function BidderDashboard() {
  const reduceMotion = useReducedMotion()
  const [bids, setBids] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getMyBids()
      .then(setBids)
      .catch(() => setError('Could not load your bids. Is the backend running?'))
  }, [])

  const applied = bids?.length ?? null
  const evaluating = bids?.filter((b) => b.status === 'submitted' || b.status === 'under_evaluation').length ?? null
  const passed = bids?.filter((b) => b.status === 'stage1_passed').length ?? null
  const notSelected = bids?.filter((b) => b.status === 'stage1_failed').length ?? null

  return (
    <div className="flex min-h-screen flex-col bg-canvas text-ink">
      <Nav />

      <Container className="flex-1">
        <div className="flex items-center justify-between border-b border-line py-4">
          <div className="flex items-center gap-2 text-sm text-subtle">
            <span className="font-medium text-ink">Bidder</span>
            <ChevronRight size={14} />
            <span>My Bids</span>
          </div>
          <Link to="/bids" className="text-sm text-accent hover:underline">
            Browse published bids
          </Link>
        </div>

        <main className="py-10">
          <h1 className="text-2xl font-semibold text-ink">My Bids</h1>
          <p className="mt-1 text-sm text-subtle">
            Bids you&apos;ve applied to, and their status once evaluation runs after each bid's closing date.
          </p>

          <div className="mt-6">
            <KpiStrip>
              <KpiCard icon={FileStack} label="Applied" value={applied ?? '—'} index={0} />
              <KpiCard icon={Clock} label="Under evaluation" value={evaluating ?? '—'} index={1} />
              <KpiCard icon={CheckCircle2} label="Passed Stage 1" value={passed ?? '—'} index={2} />
              <KpiCard icon={XCircle} label="Not selected" value={notSelected ?? '—'} index={3} />
            </KpiStrip>
          </div>

          <div className="mt-8">
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
                <FileStack size={28} className="text-subtle/50" />
                <p className="text-sm font-medium text-ink">You haven&apos;t applied to any bids yet</p>
                <Link to="/bids" className="text-xs font-medium text-accent hover:underline">
                  Browse published bids
                </Link>
              </div>
            )}

            {bids?.length > 0 && (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {bids.map((bid, i) => (
                  <motion.div
                    key={bid.bid_id}
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
                      <p className="mt-3 line-clamp-2 text-sm font-medium text-ink">{bid.rfp_title}</p>
                      <div className="mt-auto flex items-center justify-between pt-4 text-xs text-subtle">
                        <span>Submitted {new Date(bid.submitted_at).toLocaleDateString()}</span>
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
