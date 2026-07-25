import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ChevronLeft, ChevronRight, Download, FileCheck2, Info, Loader2 } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { bidDocumentUrl, getBidDetail } from '../api/client'
import Nav from '../components/Nav'

function formatDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export default function BidDetail() {
  const { isAuthenticated, role } = useAuth()
  const navigate = useNavigate()
  const { rfpId } = useParams()
  const [bid, setBid] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getBidDetail(rfpId)
      .then(setBid)
      .catch(() => setError('Could not load this bid. It may not be published, or the backend is unreachable.'))
  }, [rfpId])

  function handleApply() {
    if (!isAuthenticated) {
      navigate('/bidder/login')
      return
    }
    if (role !== 'bidder') return // a buyer/admin viewing this shouldn't apply
    navigate(`/bidder/submit/${rfpId}`)
  }

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <Nav />

      <div className="mx-auto max-w-3xl px-6">
        <div className="flex items-center justify-between border-b border-line py-4">
          <div className="flex items-center gap-2 text-sm text-subtle">
            <Link to="/bids" className="flex items-center gap-1 hover:text-ink">
              <ChevronLeft size={14} />
              Published Bids
            </Link>
            <ChevronRight size={14} />
            <span className="font-medium text-ink">{rfpId}</span>
          </div>
        </div>

        <main className="py-10">
          {error && (
            <p className="rounded-md border border-danger-line bg-danger-soft px-4 py-3 text-sm text-danger">
              {error}
            </p>
          )}

          {!error && bid === null && (
            <div className="flex items-center gap-2 text-sm text-subtle">
              <Loader2 size={16} className="animate-spin" />
              Loading...
            </div>
          )}

          {bid && (
            <>
              <div className="flex items-start justify-between gap-4">
                <h1 className="text-2xl font-semibold text-ink">{bid.title}</h1>
                <a
                  href={bidDocumentUrl(rfpId)}
                  target="_blank"
                  rel="noreferrer"
                  className="flex shrink-0 items-center gap-1.5 rounded-md border border-line bg-elevated px-3 py-1.5 text-xs font-medium text-ink transition-colors duration-200 hover:border-accent/40"
                >
                  <Download size={13} />
                  Download PDF
                </a>
              </div>
              <p className="mt-1 text-sm text-subtle">
                {bid.buyer_org}
                {bid.gem_bid_number && (
                  <span className="ml-2 font-mono text-xs text-subtle/70">{bid.gem_bid_number}</span>
                )}
              </p>

              <dl className="mt-4 grid grid-cols-2 gap-4 text-sm sm:grid-cols-5">
                <div className="rounded-md border border-line bg-elevated px-3 py-2">
                  <dt className="text-xs text-subtle">Category</dt>
                  <dd className="mt-0.5 font-medium text-ink">{bid.category}</dd>
                </div>
                <div className="rounded-md border border-line bg-elevated px-3 py-2">
                  <dt className="text-xs text-subtle">Evaluation</dt>
                  <dd className="mt-0.5 font-medium text-ink">{bid.evaluation_method}</dd>
                </div>
                <div className="rounded-md border border-line bg-elevated px-3 py-2">
                  <dt className="text-xs text-subtle">Criteria</dt>
                  <dd className="mt-0.5 font-medium text-ink">{bid.criteria_count}</dd>
                </div>
                <div className="rounded-md border border-line bg-elevated px-3 py-2">
                  <dt className="text-xs text-subtle">Mandatory</dt>
                  <dd className="mt-0.5 font-medium text-ink">{bid.mandatory_criteria_count}</dd>
                </div>
                <div className="rounded-md border border-line bg-elevated px-3 py-2">
                  <dt className="text-xs text-subtle">Closes</dt>
                  <dd className="mt-0.5 font-medium text-ink">{formatDate(bid.closing_date)}</dd>
                </div>
              </dl>

              <div className="mt-8">
                <h2 className="text-sm font-semibold text-ink">Documents you need to submit</h2>
                {bid.required_documents.length === 0 ? (
                  <p className="mt-2 text-sm text-subtle">
                    This bid doesn&apos;t list specific required document types — check the full tender
                    document above.
                  </p>
                ) : (
                  <ul className="mt-3 space-y-2">
                    {bid.required_documents.map((doc) => (
                      <li
                        key={doc}
                        className="flex items-center gap-3 rounded-md border border-line bg-elevated px-4 py-3"
                      >
                        <FileCheck2 size={16} className="shrink-0 text-accent" />
                        <span className="text-sm text-ink">{doc}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="mt-6 flex gap-3 rounded-md border border-accent/30 bg-accent/5 px-4 py-3">
                <Info size={16} className="mt-0.5 shrink-0 text-accent" />
                <p className="text-xs text-subtle">
                  <span className="font-medium text-ink">How to submit:</span> upload one file per
                  document above, and name each file exactly after the document it covers (e.g.
                  &quot;Experience Criteria.pdf&quot;, not a combined or differently-named file). This
                  keeps your submission checked quickly and correctly -- a combined or unclearly-named
                  file may be flagged as missing even if the content is present.
                </p>
              </div>

              {bid.status === 'published' ? (
                <button
                  onClick={handleApply}
                  className="mt-8 rounded-md bg-accent px-6 py-2.5 text-sm font-medium text-white transition-all duration-200 hover:scale-[1.01] hover:bg-accent-hover"
                >
                  Apply
                </button>
              ) : (
                <p className="mt-8 text-sm text-subtle">
                  This bid is no longer accepting submissions ({bid.status}).
                </p>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  )
}
