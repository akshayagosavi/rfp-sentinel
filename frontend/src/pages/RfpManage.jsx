import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  Banknote,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Lock,
  Scale,
  Trophy,
  XCircle,
} from 'lucide-react'
import {
  closeRfp,
  getBidDetail,
  getCriteria,
  getEvaluation,
  openFinancialBids,
  resolvePendingEvidence,
  runL1Selection,
} from '../api/client'
import Nav from '../components/Nav'
import Container from '../components/Container'
import Footer from '../components/Footer'

const POLL_INTERVAL_MS = 4000

const BID_STATUS_META = {
  submitted: { label: 'Awaiting evaluation', className: 'border-line bg-surface text-subtle' },
  under_evaluation: { label: 'Evaluating...', className: 'border-accent/30 bg-accent/10 text-accent' },
  stage1_passed: { label: 'Stage 1 passed', className: 'border-success-line bg-success-soft text-success' },
  stage1_failed: { label: 'Stage 1 failed', className: 'border-danger-line bg-danger-soft text-danger' },
}

function BidStatusChip({ status }) {
  const meta = BID_STATUS_META[status] ?? BID_STATUS_META.submitted
  return (
    <span className={`flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium ${meta.className}`}>
      {status === 'under_evaluation' && <Loader2 size={11} className="animate-spin" />}
      {status === 'stage1_passed' && <CheckCircle2 size={11} />}
      {status === 'stage1_failed' && <XCircle size={11} />}
      {meta.label}
    </span>
  )
}

function formatDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function formatPrice(price) {
  return `₹${price.toLocaleString('en-IN')}`
}

// A mandatory criterion the model came back 'not_found' on -- content
// wasn't found either way, so it's neither auto-passed nor auto-failed
// (see score_stage1's docstring). A human has to look and decide, with
// reasoning recorded, same as Checkpoint A's override flow.
function PendingCriterionResolver({ criterionText, onResolve }) {
  const [verdict, setVerdict] = useState('pass')
  const [reasoning, setReasoning] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await onResolve(verdict, reasoning)
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not save this resolution.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-md border border-line bg-canvas p-3">
      <p className="text-xs text-ink">{criterionText}</p>
      <p className="mt-1 text-xs text-subtle">
        No matching content was found in the bidder&apos;s documents for this mandatory criterion --
        that could mean the bidder doesn&apos;t meet it, or it could mean the content is there but
        phrased differently than the search expected. Review the bid&apos;s documents and decide.
      </p>
      <div className="mt-2 flex items-center gap-4">
        <label className="flex items-center gap-1.5 text-xs text-ink">
          <input type="radio" name={`verdict-${criterionText}`} checked={verdict === 'pass'} onChange={() => setVerdict('pass')} />
          Confirm pass
        </label>
        <label className="flex items-center gap-1.5 text-xs text-ink">
          <input type="radio" name={`verdict-${criterionText}`} checked={verdict === 'fail'} onChange={() => setVerdict('fail')} />
          Confirm fail
        </label>
      </div>
      <textarea
        required
        value={reasoning}
        onChange={(e) => setReasoning(e.target.value)}
        placeholder="Why? (required -- kept as a permanent audit record)"
        rows={2}
        className="mt-2 w-full rounded-md border border-line bg-elevated px-2.5 py-1.5 text-xs text-ink transition-colors duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
      />
      <button
        type="submit"
        disabled={submitting}
        className="mt-2 rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink transition-colors duration-200 hover:border-accent/40 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {submitting ? 'Saving...' : 'Save resolution'}
      </button>
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </form>
  )
}

export default function RfpManage() {
  const { rfpId } = useParams()
  const [bid, setBid] = useState(null) // RFP detail, reusing the public bid-detail shape
  const [evaluation, setEvaluation] = useState(null)
  const [criteriaById, setCriteriaById] = useState({})
  const [loadError, setLoadError] = useState('')
  const [closing, setClosing] = useState(false)
  const [closeError, setCloseError] = useState('')
  const [opening, setOpening] = useState(false)
  const [openError, setOpenError] = useState('')
  const [msePreference, setMsePreference] = useState(true)
  const [runningL1, setRunningL1] = useState(false)
  const [l1Error, setL1Error] = useState('')
  const pollTimer = useRef(null)
  // Tracks "Open Financial Bids was triggered, Stage 2 hasn't landed yet" --
  // a ref, not state, so the recursive polling closure below always reads
  // the latest value instead of the one captured when it was first created.
  const awaitingStage2 = useRef(false)

  const loadEvaluation = useCallback(() => {
    getEvaluation(rfpId)
      .then((data) => {
        setEvaluation(data)
        if (data.stage2_result) awaitingStage2.current = false
        const stage1Working = data.bids.some((b) => b.status === 'submitted' || b.status === 'under_evaluation')
        const stage2Working = awaitingStage2.current
        if (stage1Working || stage2Working) {
          pollTimer.current = setTimeout(loadEvaluation, POLL_INTERVAL_MS)
        }
      })
      .catch(() => setLoadError('Could not load evaluation results.'))
  }, [rfpId])

  useEffect(() => {
    getBidDetail(rfpId)
      .then(setBid)
      .catch(() => setLoadError('Could not load this RFP.'))
    loadEvaluation()
    // Criteria text is only needed once bids are in review (to label
    // pending_criteria ids with real text) -- fetch it once regardless,
    // it's cheap and avoids re-fetching every poll tick.
    getCriteria(rfpId)
      .then(({ criteria }) => setCriteriaById(Object.fromEntries(criteria.map((c) => [c.id, c.text]))))
      .catch(() => {})
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current)
    }
  }, [rfpId, loadEvaluation])

  async function handleResolve(bidId, criterionId, verdict, reasoning) {
    await resolvePendingEvidence(rfpId, bidId, criterionId, verdict, reasoning)
    loadEvaluation()
  }

  async function handleClose() {
    setClosing(true)
    setCloseError('')
    try {
      await closeRfp(rfpId)
      const fresh = await getBidDetail(rfpId)
      setBid(fresh)
      loadEvaluation()
    } catch (err) {
      setCloseError(err.response?.data?.detail || 'Could not close this RFP.')
    } finally {
      setClosing(false)
    }
  }

  async function handleOpenFinancialBids() {
    setOpening(true)
    setOpenError('')
    try {
      await openFinancialBids(rfpId)
      awaitingStage2.current = true
      loadEvaluation()
    } catch (err) {
      setOpenError(err.response?.data?.detail || 'Could not open financial bids.')
    } finally {
      setOpening(false)
    }
  }

  async function handleRunL1Selection() {
    setRunningL1(true)
    setL1Error('')
    try {
      await runL1Selection(rfpId, msePreference)
      loadEvaluation()
    } catch (err) {
      setL1Error(err.response?.data?.detail || 'Could not run L1 selection.')
    } finally {
      setRunningL1(false)
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-canvas text-ink">
      <Nav />

      <Container className="flex-1">
        <div className="flex items-center gap-2 border-b border-line py-4 text-sm text-subtle">
          <Link to="/buyer/rfps" className="flex items-center gap-1 hover:text-ink">
            <ChevronLeft size={14} />
            My RFPs
          </Link>
          <ChevronRight size={14} />
          <span className="font-medium text-ink">{rfpId}</span>
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
            <>
              <h1 className="text-2xl font-semibold text-ink">{bid.title}</h1>
              <p className="mt-1 text-sm text-subtle">
                {bid.status === 'published'
                  ? `Open for submissions until ${formatDate(bid.closing_date)}`
                  : `Status: ${bid.status}`}
              </p>

              {bid.status === 'published' && (
                <div className="mt-6 rounded-card border border-line bg-elevated p-5">
                  <h2 className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                    <Lock size={13} className="text-subtle" />
                    Close submissions
                  </h2>
                  <p className="mt-1 text-xs text-subtle">
                    Normally this RFP closes on its own once {formatDate(bid.closing_date)} passes. Use the
                    button below to close it now and start Stage 1 (technical) evaluation immediately --
                    a manual override for demos, so you don&apos;t have to wait out the real bid period.
                  </p>
                  <button
                    onClick={handleClose}
                    disabled={closing}
                    className="mt-4 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition-all duration-200 hover:scale-[1.01] hover:bg-accent-hover disabled:opacity-60"
                  >
                    {closing ? 'Closing...' : 'Close & Evaluate Now'}
                  </button>
                  {closeError && <p className="mt-3 text-sm text-danger">{closeError}</p>}
                </div>
              )}

              {bid.status !== 'published' && (
                <div className="mt-8">
                  <h2 className="text-sm font-semibold text-ink">Bids ({evaluation?.bids.length ?? 0})</h2>
                  <p className="mt-1 text-xs text-subtle">
                    Stage 1 checks every bid&apos;s Packet-I (technical) documents against your approved
                    criteria.
                  </p>

                  {evaluation?.bids.length === 0 && (
                    <p className="mt-4 rounded-md border border-line bg-elevated px-4 py-6 text-center text-sm text-subtle">
                      No bids were submitted before this RFP closed.
                    </p>
                  )}

                  <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
                    {evaluation?.bids.map((b) => (
                      <div key={b.bid_id} className="rounded-card border border-line bg-elevated p-4">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-sm font-medium text-ink">{b.bidder_org}</p>
                            <p className="mt-0.5 text-xs text-subtle">
                              Submitted {formatDate(b.submitted_at)}
                              {b.technical_score !== null && ` · Technical score: ${b.technical_score}/100`}
                            </p>
                          </div>
                          <BidStatusChip status={b.status} />
                        </div>
                        {b.failed_criteria.length > 0 && (
                          <div className="mt-3 flex gap-2 rounded-md border border-danger-line bg-danger-soft px-3 py-2 text-xs text-danger">
                            <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                            <span>{b.failed_criteria.length} mandatory criterion/criteria failed.</span>
                          </div>
                        )}
                        {b.pending_criteria.length > 0 && (
                          <div className="mt-3 space-y-2">
                            <div className="flex gap-2 rounded-md border border-line bg-surface px-3 py-2 text-xs text-subtle">
                              <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                              <span>
                                {b.pending_criteria.length} mandatory criterion/criteria need human review
                                before financial bids can be opened.
                              </span>
                            </div>
                            {b.pending_criteria.map((criterionId) => (
                              <PendingCriterionResolver
                                key={criterionId}
                                criterionText={criteriaById[criterionId] ?? criterionId}
                                onResolve={(verdict, reasoning) => handleResolve(b.bid_id, criterionId, verdict, reasoning)}
                              />
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                  {bid.status === 'closed' &&
                    !awaitingStage2.current &&
                    evaluation &&
                    evaluation.bids.length > 0 &&
                    evaluation.bids.every((b) => b.status === 'stage1_passed' || b.status === 'stage1_failed') &&
                    !evaluation.bids.some((b) => b.status === 'stage1_passed' && b.pending_criteria.length > 0) && (
                      <div className="mt-6 rounded-card border border-line bg-elevated p-5">
                        <h2 className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                          <Banknote size={13} className="text-subtle" />
                          Open financial bids
                        </h2>
                        <p className="mt-1 text-xs text-subtle">
                          Stage 1 is complete. Opening financial bids reads the sealed price document
                          (Packet-II) for every bid that passed Stage 1 -- and only those -- then ranks
                          them by price. A technically disqualified bidder&apos;s price is never opened,
                          matching the real two-envelope procurement principle.
                        </p>
                        <button
                          onClick={handleOpenFinancialBids}
                          disabled={opening}
                          className="mt-4 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition-all duration-200 hover:scale-[1.01] hover:bg-accent-hover disabled:opacity-60"
                        >
                          {opening ? 'Opening...' : 'Open Financial Bids'}
                        </button>
                        {openError && <p className="mt-3 text-sm text-danger">{openError}</p>}
                      </div>
                    )}

                  {bid.status === 'closed' && awaitingStage2.current && (
                    <div className="mt-6 flex items-center gap-2 rounded-md border border-line bg-elevated px-4 py-3 text-sm text-subtle">
                      <Loader2 size={15} className="animate-spin" />
                      Extracting prices and ranking Stage-1-qualified bids...
                    </div>
                  )}

                  {evaluation?.stage2_result && evaluation.stage2_result.evaluation_method === 'QCBS' && (
                    <div className="mt-8">
                      <h2 className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                        <Scale size={13} className="text-subtle" />
                        Financial ranking (Stage 2) -- QCBS
                      </h2>
                      <p className="mt-1 text-xs text-subtle">
                        This RFP specifies Quality and Cost Based Selection: each bid&apos;s technical
                        score and price score are blended ({Math.round(evaluation.stage2_result.technical_weight * 100)}% technical /{' '}
                        {Math.round(evaluation.stage2_result.price_weight * 100)}% price) into one final
                        score. The highest final score wins -- not necessarily the cheapest bid. Only
                        Stage-1-passed, Class-I/II local-supplier bids are ranked.
                      </p>

                      {evaluation.stage2_result.ranking.length === 0 ? (
                        <p className="mt-4 rounded-md border border-line bg-elevated px-4 py-6 text-center text-sm text-subtle">
                          No Stage-1-passed, local-supplier bids to rank.
                        </p>
                      ) : (
                        <ul className="mt-4 space-y-2">
                          {evaluation.stage2_result.ranking.map((r, i) => {
                            const org = evaluation.bids.find((b) => b.bid_id === r.bid_id)?.bidder_org
                            const isWinner = evaluation.stage2_result.winner === r.bid_id
                            return (
                              <li
                                key={r.bid_id}
                                className={`rounded-card border px-4 py-3 ${
                                  isWinner ? 'border-success-line bg-success-soft' : 'border-line bg-elevated'
                                }`}
                              >
                                <div className="flex items-center justify-between gap-3">
                                  <div className="flex items-center gap-3">
                                    <span className="text-xs font-medium text-subtle">#{i + 1}</span>
                                    <p className="text-sm font-medium text-ink">{org}</p>
                                  </div>
                                  {isWinner && (
                                    <span className="flex items-center gap-1 rounded-full border border-success-line bg-success-soft px-2.5 py-0.5 text-xs font-medium text-success">
                                      <Trophy size={11} />
                                      Winner
                                    </span>
                                  )}
                                </div>
                                <div className="mt-2 grid grid-cols-4 gap-2 text-xs text-subtle">
                                  <div>
                                    <p className="text-subtle/70">Price</p>
                                    <p className="font-medium text-ink">{formatPrice(r.price)}</p>
                                  </div>
                                  <div>
                                    <p className="text-subtle/70">Technical</p>
                                    <p className="font-medium text-ink">{r.technical_score}/100</p>
                                  </div>
                                  <div>
                                    <p className="text-subtle/70">Price score</p>
                                    <p className="font-medium text-ink">{r.price_score}/100</p>
                                  </div>
                                  <div>
                                    <p className="text-subtle/70">Final score</p>
                                    <p className="font-medium text-ink">{r.final_score}</p>
                                  </div>
                                </div>
                              </li>
                            )
                          })}
                        </ul>
                      )}
                    </div>
                  )}

                  {evaluation?.stage2_result && evaluation.stage2_result.evaluation_method !== 'QCBS' && (
                    <div className="mt-8">
                      <h2 className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                        <Scale size={13} className="text-subtle" />
                        Financial ranking (Stage 2) -- L1
                      </h2>
                      <p className="mt-1 text-xs text-subtle">
                        Lowest price wins (L1). Only Stage-1-passed, Class-I/II local-supplier bids are
                        ranked -- a non-local bid is excluded here regardless of price, per the RFP&apos;s
                        Make in India requirement.
                      </p>

                      {evaluation.stage2_result.ranking.length === 0 ? (
                        <p className="mt-4 rounded-md border border-line bg-elevated px-4 py-6 text-center text-sm text-subtle">
                          No Stage-1-passed, local-supplier bids to rank.
                        </p>
                      ) : (
                        <ul className="mt-4 space-y-2">
                          {evaluation.stage2_result.ranking.map((r, i) => {
                            const org = evaluation.bids.find((b) => b.bid_id === r.bid_id)?.bidder_org
                            const isTied = evaluation.stage2_result.tied_for_l1.includes(r.bid_id)
                            const isWinner = evaluation.stage2_result.l1_winner === r.bid_id
                            const isOutrightL1 = i === 0 && evaluation.stage2_result.tied_for_l1.length === 0
                            return (
                              <li
                                key={r.bid_id}
                                className={`flex items-center justify-between gap-3 rounded-card border px-4 py-3 ${
                                  isWinner || isOutrightL1
                                    ? 'border-success-line bg-success-soft'
                                    : 'border-line bg-elevated'
                                }`}
                              >
                                <div className="flex items-center gap-3">
                                  <span className="text-xs font-medium text-subtle">#{i + 1}</span>
                                  <div>
                                    <p className="text-sm font-medium text-ink">{org}</p>
                                    <p className="text-xs text-subtle">{formatPrice(r.price)}</p>
                                  </div>
                                </div>
                                <div className="flex items-center gap-2">
                                  {isWinner && (
                                    <span className="flex items-center gap-1 rounded-full border border-success-line bg-success-soft px-2.5 py-0.5 text-xs font-medium text-success">
                                      <Trophy size={11} />
                                      L1 (tie-break winner)
                                    </span>
                                  )}
                                  {!isWinner && isOutrightL1 && (
                                    <span className="flex items-center gap-1 rounded-full border border-success-line bg-success-soft px-2.5 py-0.5 text-xs font-medium text-success">
                                      <Trophy size={11} />
                                      L1
                                    </span>
                                  )}
                                  {!isWinner && isTied && (
                                    <span className="rounded-full border border-accent/30 bg-accent/10 px-2.5 py-0.5 text-xs font-medium text-accent">
                                      Tied for L1
                                    </span>
                                  )}
                                </div>
                              </li>
                            )
                          })}
                        </ul>
                      )}

                      {evaluation.stage2_result.mse_price_match && (
                        <div
                          className={`mt-4 rounded-card border p-5 ${
                            evaluation.stage2_result.mse_price_match.activated
                              ? 'border-accent/30 bg-accent/5'
                              : 'border-line bg-elevated'
                          }`}
                        >
                          <h3 className="text-sm font-semibold text-ink">
                            MSE price-match {evaluation.stage2_result.mse_price_match.activated ? '-- activated' : '-- not activated'}
                          </h3>
                          <p className="mt-1 text-xs text-subtle">{evaluation.stage2_result.mse_price_match.reasoning}</p>
                          {evaluation.stage2_result.mse_price_match.activated && (
                            <p className="mt-2 text-xs text-ink">
                              Quantity split: L1 gets {evaluation.stage2_result.mse_price_match.l1_share_percent}%,
                              matching MSE bidder gets {evaluation.stage2_result.mse_price_match.mse_share_percent}%.
                            </p>
                          )}
                        </div>
                      )}

                      {evaluation.stage2_result.tied_for_l1.length > 1 && !evaluation.stage2_result.l1_winner && (
                        <div className="mt-4 rounded-card border border-accent/30 bg-accent/5 p-5">
                          <h3 className="text-sm font-semibold text-ink">Resolve the L1 tie</h3>
                          <p className="mt-1 text-xs text-subtle">
                            {evaluation.stage2_result.tied_for_l1.length} bidders quoted the same lowest
                            price. This mirrors GeM&apos;s own &quot;Run L1 Selection&quot; feature: a
                            random draw among the tied bidders, restricted to MSE bidders within the tie
                            if MSE purchase preference is active for this RFP.
                          </p>
                          <label className="mt-3 flex items-center gap-2 text-sm text-ink">
                            <input
                              type="checkbox"
                              checked={msePreference}
                              onChange={(e) => setMsePreference(e.target.checked)}
                            />
                            MSE purchase preference is active for this RFP
                          </label>
                          <button
                            onClick={handleRunL1Selection}
                            disabled={runningL1}
                            className="mt-4 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition-all duration-200 hover:scale-[1.01] hover:bg-accent-hover disabled:opacity-60"
                          >
                            {runningL1 ? 'Running...' : 'Run L1 Selection'}
                          </button>
                          {l1Error && <p className="mt-3 text-sm text-danger">{l1Error}</p>}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </main>
      </Container>

      <Footer slim />
    </div>
  )
}
