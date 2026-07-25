import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { AlertTriangle, CheckCircle2, ChevronLeft, Circle, Loader2, Lock, UploadCloud, X } from 'lucide-react'
import { getBidDetail, submitBid } from '../api/client'
import Nav from '../components/Nav'
import Container from '../components/Container'
import Footer from '../components/Footer'

// GeM RFP templates list some required docs as generic, numbered
// placeholders ("Additional Doc 1 (Requested in ATC)", "...Doc 2...")
// whose real meaning only lives in the RFP's free-text ATC section -- there
// is no distinguishing name to give a bidder a dedicated upload slot for.
// Grouped into one multi-file picker instead of N individually-labeled
// slots the bidder has no way to fill correctly. Mirrors the backend's own
// grouping in check_document_completeness.py.
const GENERIC_ATC_PATTERN = /^Additional Doc \d+/i

// One guided upload slot per required document -- displays the exact
// expected label so the bidder names/picks the right file, matching the
// "how to submit" guidance already shown on the bid detail page. The
// backend's completeness check is the real, authoritative gate; this is
// just a friendlier way to fill it out than one generic multi-file picker.
function DocumentSlot({ label, file, onChange }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-line bg-elevated px-4 py-3">
      <div className="min-w-0">
        <p className="text-sm font-medium text-ink">{label}</p>
        {file && <p className="mt-0.5 truncate text-xs text-subtle">{file.name}</p>}
      </div>
      {file ? (
        <button
          type="button"
          onClick={() => onChange(null)}
          className="flex shrink-0 items-center gap-1 rounded-md border border-line px-2.5 py-1.5 text-xs text-subtle transition-colors duration-200 hover:border-danger-line hover:text-danger"
        >
          <X size={12} />
          Remove
        </button>
      ) : (
        <label className="flex shrink-0 cursor-pointer items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-xs font-medium text-accent transition-colors duration-200 hover:border-accent/40">
          <UploadCloud size={12} />
          Choose file
          <input
            type="file"
            accept="application/pdf"
            className="hidden"
            onChange={(e) => onChange(e.target.files?.[0] ?? null)}
          />
        </label>
      )}
    </div>
  )
}

// One combined slot for however many generic "Additional Doc N" placeholders
// the RFP lists -- accepts multiple PDFs at once, since there's no way to
// tell a bidder which file goes in which numbered slot.
function GenericDocsSlot({ count, files, onChange }) {
  return (
    <div className="rounded-md border border-line bg-elevated px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink">Additional ATC documents ({count} required)</p>
          <p className="mt-0.5 text-xs text-subtle">
            See the RFP's ATC section for what these should contain. Upload {count} file{count === 1 ? '' : 's'}.
          </p>
        </div>
        <label className="flex shrink-0 cursor-pointer items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-xs font-medium text-accent transition-colors duration-200 hover:border-accent/40">
          <UploadCloud size={12} />
          Add files
          <input
            type="file"
            accept="application/pdf"
            multiple
            className="hidden"
            onChange={(e) => {
              const picked = Array.from(e.target.files ?? [])
              if (picked.length) onChange([...files, ...picked])
              e.target.value = ''
            }}
          />
        </label>
      </div>
      {files.length > 0 && (
        <ul className="mt-2 space-y-1">
          {files.map((file, i) => (
            <li key={`${file.name}-${i}`} className="flex items-center justify-between gap-2 text-xs text-subtle">
              <span className="truncate">{file.name}</span>
              <button
                type="button"
                onClick={() => onChange(files.filter((_, idx) => idx !== i))}
                className="shrink-0 text-subtle hover:text-danger"
              >
                <X size={12} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ProgressItem({ done, label }) {
  return (
    <li className="flex items-center gap-2 text-xs">
      {done ? (
        <CheckCircle2 size={14} className="shrink-0 text-success" />
      ) : (
        <Circle size={14} className="shrink-0 text-subtle/40" />
      )}
      <span className={done ? 'text-ink' : 'text-subtle'}>{label}</span>
    </li>
  )
}

export default function BidSubmission() {
  const { rfpId } = useParams()
  const [bid, setBid] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [filesBySlot, setFilesBySlot] = useState({})
  const [genericFiles, setGenericFiles] = useState([])
  const [financialDocument, setFinancialDocument] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [missing, setMissing] = useState(null)
  const [submitError, setSubmitError] = useState('')
  const [success, setSuccess] = useState(false)

  useEffect(() => {
    getBidDetail(rfpId)
      .then(setBid)
      .catch(() => setLoadError('Could not load this bid.'))
  }, [rfpId])

  const namedDocs = bid?.required_documents.filter((doc) => !GENERIC_ATC_PATTERN.test(doc)) ?? []
  const genericCount = (bid?.required_documents.length ?? 0) - namedDocs.length
  const namedSlotsFilled = namedDocs.every((doc) => filesBySlot[doc])
  const genericSlotFilled = genericCount === 0 || genericFiles.length >= genericCount
  const allSlotsFilled = namedSlotsFilled && genericSlotFilled
  const canSubmit = allSlotsFilled && financialDocument && !submitting

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    setMissing(null)
    setSubmitError('')
    try {
      const files = [...Object.values(filesBySlot).filter(Boolean), ...genericFiles]
      await submitBid(rfpId, files, financialDocument)
      setSuccess(true)
    } catch (err) {
      if (err.response?.status === 422) {
        setMissing(err.response.data.detail.missing)
      } else if (err.response?.status === 409) {
        setSubmitError('You have already submitted a bid for this RFP.')
      } else {
        setSubmitError('Submission failed. Is the backend running?')
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (success) {
    return (
      <div className="flex min-h-screen flex-col bg-canvas text-ink">
        <Nav />
        <Container className="flex-1">
          <main className="py-16 text-center">
            <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-success-soft text-success">
              <CheckCircle2 size={22} />
            </span>
            <h1 className="mt-4 text-xl font-semibold text-ink">Submitted</h1>
            <p className="mx-auto mt-2 max-w-sm text-sm text-subtle">
              Your bid is recorded and will be evaluated after the bid closes.
            </p>
            <Link
              to="/bidder/dashboard"
              className="mt-6 inline-block rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition-all duration-200 hover:scale-[1.01] hover:bg-accent-hover"
            >
              Go to My Bids
            </Link>
          </main>
        </Container>
        <Footer slim />
      </div>
    )
  }

  return (
    <div className="flex min-h-screen flex-col bg-canvas text-ink">
      <Nav />
      <Container className="flex-1">
        <div className="border-b border-line py-4">
          <Link to={`/bids/${rfpId}`} className="flex items-center gap-1 text-sm text-subtle hover:text-ink">
            <ChevronLeft size={14} />
            Back to bid
          </Link>
        </div>

        <main className="py-10">
          {loadError && (
            <p className="rounded-md border border-danger-line bg-danger-soft px-4 py-3 text-sm text-danger">
              {loadError}
            </p>
          )}

          {!loadError && bid === null && (
            <div className="flex items-center gap-2 text-sm text-subtle">
              <Loader2 size={16} className="animate-spin" />
              Loading...
            </div>
          )}

          {bid && (
            <form onSubmit={handleSubmit}>
              <h1 className="text-2xl font-semibold text-ink">Submit your bid</h1>
              <p className="mt-1 text-sm text-subtle">{bid.title}</p>

              <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
                <div className="space-y-6 lg:col-span-2">
                  <div className="rounded-card border border-line bg-elevated p-5">
                    <h2 className="text-sm font-semibold text-ink">Required documents</h2>
                    <div className="mt-3 space-y-2">
                      {namedDocs.map((doc) => (
                        <DocumentSlot
                          key={doc}
                          label={doc}
                          file={filesBySlot[doc]}
                          onChange={(file) => setFilesBySlot((prev) => ({ ...prev, [doc]: file }))}
                        />
                      ))}
                      {genericCount > 0 && (
                        <GenericDocsSlot count={genericCount} files={genericFiles} onChange={setGenericFiles} />
                      )}
                    </div>

                    {missing && (
                      <div className="mt-4 flex gap-3 rounded-md border border-danger-line bg-danger-soft px-4 py-3">
                        <AlertTriangle size={16} className="mt-0.5 shrink-0 text-danger" />
                        <div className="text-sm text-danger">
                          <p className="font-medium">Submission incomplete -- fix these and resubmit:</p>
                          <ul className="mt-1 list-inside list-disc">
                            {missing.map((doc) => (
                              <li key={doc}>{doc}</li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="rounded-card border border-line bg-elevated p-5">
                    <h2 className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                      <Lock size={13} className="text-subtle" />
                      Financial bid
                    </h2>
                    <p className="mt-1 text-xs text-subtle">
                      Upload your price schedule / BOQ as a PDF. It stays sealed and is only opened after the
                      bid closes -- do not enter a price anywhere else.
                    </p>
                    <div className="mt-3">
                      <DocumentSlot
                        label="Price schedule (Packet-II)"
                        file={financialDocument}
                        onChange={setFinancialDocument}
                      />
                    </div>
                  </div>
                </div>

                <div className="lg:col-span-1">
                  <div className="rounded-card border border-line bg-elevated p-5 lg:sticky lg:top-20">
                    <h2 className="text-sm font-semibold text-ink">Submission checklist</h2>
                    <ul className="mt-3 space-y-2.5">
                      <ProgressItem done={namedSlotsFilled} label={`${namedDocs.length} required document(s)`} />
                      {genericCount > 0 && (
                        <ProgressItem done={genericSlotFilled} label={`${genericCount} additional ATC document(s)`} />
                      )}
                      <ProgressItem done={!!financialDocument} label="Sealed financial bid" />
                    </ul>

                    {submitError && (
                      <p className="mt-4 rounded-md border border-danger-line bg-danger-soft px-3 py-2 text-xs text-danger">
                        {submitError}
                      </p>
                    )}

                    <button
                      type="submit"
                      disabled={!canSubmit}
                      className={`mt-4 w-full rounded-md px-4 py-2.5 text-sm font-medium transition-all duration-200 ${
                        canSubmit
                          ? 'bg-accent text-white hover:scale-[1.01] hover:bg-accent-hover'
                          : 'cursor-not-allowed border border-line bg-surface text-subtle'
                      }`}
                    >
                      {submitting ? 'Submitting...' : 'Submit bid'}
                    </button>
                  </div>
                </div>
              </div>
            </form>
          )}
        </main>
      </Container>
      <Footer slim />
    </div>
  )
}
