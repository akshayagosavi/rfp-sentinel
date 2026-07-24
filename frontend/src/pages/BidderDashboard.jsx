import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight, FileText, Loader2 } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { getBidderRfps } from '../api/client'
import Nav from '../components/Nav'

export default function BidderDashboard() {
  const { logout } = useAuth()
  const [rfps, setRfps] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getBidderRfps()
      .then(setRfps)
      .catch(() => setError('Could not load published RFPs. Is the backend running?'))
  }, [])

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <Nav>
        <button
          onClick={logout}
          className="text-sm text-subtle transition-colors duration-200 hover:text-ink"
        >
          Sign out
        </button>
      </Nav>

      <div className="mx-auto max-w-3xl px-6">
        <div className="flex items-center justify-between border-b border-line py-4">
          <div className="flex items-center gap-2 text-sm text-subtle">
            <span className="font-medium text-ink">Bidder</span>
            <ChevronRight size={14} />
            <span>Published RFPs</span>
          </div>
        </div>

        <main className="py-10">
          <h1 className="text-2xl font-semibold text-ink">Published RFPs</h1>
          <p className="mt-1 text-sm text-subtle">
            Open a tender to see a summary and exactly which documents you need to submit.
          </p>

          <div className="mt-8">
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
                No RFPs have been published yet. Check back later.
              </p>
            )}

            {rfps?.length > 0 && (
              <ul className="space-y-3">
                {rfps.map((rfp) => (
                  <li key={rfp.rfp_id}>
                    <Link
                      to={`/bidder/rfp/${rfp.rfp_id}`}
                      className="flex items-center justify-between rounded-card border border-line bg-elevated px-5 py-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-md"
                    >
                      <div className="flex items-start gap-3">
                        <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent/10 text-accent">
                          <FileText size={16} />
                        </span>
                        <div>
                          <p className="text-sm font-medium text-ink">{rfp.source_file}</p>
                          <p className="mt-1 text-xs text-subtle">
                            {rfp.category} &middot; {rfp.evaluation_method} evaluation &middot;{' '}
                            {rfp.criteria_count} criteria &middot; {rfp.required_documents_count} documents required
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
