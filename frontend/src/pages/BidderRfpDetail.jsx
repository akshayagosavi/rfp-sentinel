import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronLeft, ChevronRight, FileCheck2, Info, Loader2 } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { getBidderRfpDetail } from '../api/client'
import Nav from '../components/Nav'

export default function BidderRfpDetail() {
  const { logout } = useAuth()
  const { rfpId } = useParams()
  const [rfp, setRfp] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getBidderRfpDetail(rfpId)
      .then(setRfp)
      .catch(() => setError('Could not load this RFP. It may not be published, or the backend is unreachable.'))
  }, [rfpId])

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
            <Link to="/bidder/dashboard" className="flex items-center gap-1 hover:text-ink">
              <ChevronLeft size={14} />
              Published RFPs
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

          {!error && rfp === null && (
            <div className="flex items-center gap-2 text-sm text-subtle">
              <Loader2 size={16} className="animate-spin" />
              Loading...
            </div>
          )}

          {rfp && (
            <>
              <h1 className="text-2xl font-semibold text-ink">{rfp.source_file}</h1>
              <dl className="mt-4 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
                <div className="rounded-md border border-line bg-elevated px-3 py-2">
                  <dt className="text-xs text-subtle">Category</dt>
                  <dd className="mt-0.5 font-medium text-ink">{rfp.category}</dd>
                </div>
                <div className="rounded-md border border-line bg-elevated px-3 py-2">
                  <dt className="text-xs text-subtle">Evaluation</dt>
                  <dd className="mt-0.5 font-medium text-ink">{rfp.evaluation_method}</dd>
                </div>
                <div className="rounded-md border border-line bg-elevated px-3 py-2">
                  <dt className="text-xs text-subtle">Criteria</dt>
                  <dd className="mt-0.5 font-medium text-ink">{rfp.criteria_count}</dd>
                </div>
                <div className="rounded-md border border-line bg-elevated px-3 py-2">
                  <dt className="text-xs text-subtle">Mandatory</dt>
                  <dd className="mt-0.5 font-medium text-ink">{rfp.mandatory_criteria_count}</dd>
                </div>
              </dl>

              <div className="mt-8">
                <h2 className="text-sm font-semibold text-ink">Documents you need to submit</h2>
                {rfp.required_documents.length === 0 ? (
                  <p className="mt-2 text-sm text-subtle">
                    This RFP doesn&apos;t list specific required document types -- check the full tender
                    document directly.
                  </p>
                ) : (
                  <ul className="mt-3 space-y-2">
                    {rfp.required_documents.map((doc) => (
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
            </>
          )}
        </main>
      </div>
    </div>
  )
}
