import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, ChevronRight, FileStack, Files, ScanSearch, ShieldCheck, UploadCloud, UserCheck } from 'lucide-react'
import { uploadRfp, getStatus, getCriteria, approveCriteria, getMyRfps } from '../api/client'
import RfpUploadForm from '../components/RfpUploadForm'
import EvaluationResult from '../components/EvaluationResult'
import Nav from '../components/Nav'
import Container from '../components/Container'
import Footer from '../components/Footer'
import { KpiCard, KpiStrip } from '../components/KpiStrip'

const POLL_INTERVAL_MS = 4000

// Persists the in-flight rfp_id across navigation/reload so coming back to
// this page resumes tracking it instead of showing the upload form again --
// that gap is what caused an accidental double-upload (and doubled CPU load
// from two concurrent LLM evaluations) earlier.
const ACTIVE_EVALUATION_KEY = 'rfp_sentinel_active_evaluation'

function formatElapsed(totalSeconds) {
  const m = Math.floor(totalSeconds / 60)
  const s = totalSeconds % 60
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

const PHASE_META = {
  idle: { label: 'Ready to upload', className: 'border-line bg-surface text-subtle' },
  uploading: { label: 'Uploading', className: 'border-accent/30 bg-accent/10 text-accent' },
  evaluating: { label: 'Evaluating', className: 'border-accent/30 bg-accent/10 text-accent' },
  success: { label: 'Published', className: 'border-success-line bg-success-soft text-success' },
  invalid: { label: 'Needs attention', className: 'border-danger-line bg-danger-soft text-danger' },
  error: { label: 'Error', className: 'border-danger-line bg-danger-soft text-danger' },
}

function StatusPill({ phase }) {
  const meta = PHASE_META[phase] ?? PHASE_META.idle
  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-medium ${meta.className}`}>
      {meta.label}
    </span>
  )
}

const RFP_STATUS_META = {
  published: { label: 'Open', className: 'border-success-line bg-success-soft text-success' },
  closed: { label: 'Closed', className: 'border-accent/30 bg-accent/10 text-accent' },
  evaluated: { label: 'Evaluated', className: 'border-line bg-surface text-subtle' },
}

function formatDate(iso) {
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function RecentRfpsCard({ rfps }) {
  return (
    <div className="rounded-card border border-line bg-elevated p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Recent RFPs</h2>
        <Link to="/buyer/rfps" className="text-xs font-medium text-accent hover:underline">
          View all
        </Link>
      </div>
      {rfps === null && <p className="mt-3 text-xs text-subtle">Loading...</p>}
      {rfps?.length === 0 && <p className="mt-3 text-xs text-subtle">Nothing published yet.</p>}
      {rfps?.length > 0 && (
        <ul className="mt-3 space-y-2">
          {rfps.slice(0, 5).map((rfp) => {
            const meta = RFP_STATUS_META[rfp.status] ?? RFP_STATUS_META.published
            return (
              <li key={rfp.rfp_id}>
                <Link
                  to={`/buyer/rfp/${rfp.rfp_id}`}
                  className="flex items-center justify-between gap-2 rounded-md border border-line bg-canvas px-3 py-2 transition-colors duration-200 hover:border-accent/40"
                >
                  <span className="truncate text-xs font-medium text-ink">{rfp.title}</span>
                  <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium ${meta.className}`}>
                    {meta.label}
                  </span>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

const CHECKPOINT_STEPS = [
  { icon: UploadCloud, text: 'Upload the tender PDF' },
  { icon: ScanSearch, text: 'Checked against norms + the RFP’s own rules' },
  { icon: UserCheck, text: 'You review any flagged criteria' },
  { icon: ShieldCheck, text: 'Publish — bidders can now apply' },
]

function CheckpointStepsCard() {
  return (
    <div className="rounded-card border border-line bg-elevated p-5">
      <h2 className="text-sm font-semibold text-ink">Checkpoint A flow</h2>
      <ul className="mt-3 space-y-3">
        {CHECKPOINT_STEPS.map((step, i) => (
          <li key={step.text} className="flex items-start gap-2.5">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent/10 text-accent">
              <step.icon size={12} />
            </span>
            <span className="text-xs text-subtle">
              <span className="font-medium text-ink">{i + 1}.</span> {step.text}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function BuyerDashboard() {
  // idle | uploading | evaluating | success | invalid | error
  const [phase, setPhase] = useState('idle')
  const [rfpId, setRfpId] = useState(null)
  const [record, setRecord] = useState(null)
  const [allCriteria, setAllCriteria] = useState([])
  const [flaggedCriteria, setFlaggedCriteria] = useState([])
  const [errorMessage, setErrorMessage] = useState('')
  const [startedAt, setStartedAt] = useState(null)
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const pollTimer = useRef(null)

  const [myRfps, setMyRfps] = useState(null)
  const [flaggedCount, setFlaggedCount] = useState(null)

  async function loadKpis() {
    try {
      const rfps = await getMyRfps()
      setMyRfps(rfps)
      // Real count, not illustrative -- fetches each RFP's own criteria and
      // counts flags, same data Checkpoint A itself shows. Capped at the 20
      // most recent to bound the number of requests on an established account.
      const sample = rfps.slice(0, 20)
      const criteriaLists = await Promise.all(sample.map((r) => getCriteria(r.rfp_id).catch(() => ({ criteria: [] }))))
      const count = criteriaLists.reduce(
        (sum, { criteria }) => sum + criteria.filter((c) => c.compliance_issue || c.prohibited_practice_issue).length,
        0,
      )
      setFlaggedCount(count)
    } catch {
      setMyRfps([])
      setFlaggedCount(null)
    }
  }

  function stopPolling() {
    if (pollTimer.current) {
      clearTimeout(pollTimer.current)
      pollTimer.current = null
    }
  }

  async function resolveOutcome(id, status) {
    const { criteria } = await getCriteria(id)
    setAllCriteria(criteria)
    const flagged = criteria.filter((c) => c.compliance_issue || c.prohibited_practice_issue)

    if (flagged.length > 0) {
      setFlaggedCriteria(flagged)
      setPhase('invalid')
      return
    }

    if (status !== 'approved') {
      await approveCriteria(id, criteria)
    }
    setRecord({ rfpId: id, criteriaCount: criteria.length })
    setPhase('success')
    loadKpis()
  }

  // A human reviewed the flagged criteria, disagreed with (some of) them, and
  // chose to publish anyway -- their reasoning is stored per criterion as a
  // real audit trail, not silently discarded. Requires reasoning for every
  // currently-flagged criterion (enforced in EvaluationResult) before this
  // can be called, so nothing gets published with an unaddressed flag.
  async function publishWithOverrides(reasoningById) {
    const merged = allCriteria.map((c) =>
      reasoningById[c.id] ? { ...c, override_reasoning: reasoningById[c.id] } : c
    )
    await approveCriteria(rfpId, merged)
    localStorage.removeItem(ACTIVE_EVALUATION_KEY)
    setRecord({ rfpId, criteriaCount: merged.length, overriddenCount: Object.keys(reasoningById).length })
    setPhase('success')
    loadKpis()
  }

  async function pollUntilReady(id) {
    try {
      const { status, error } = await getStatus(id)
      if (status === 'extracting' || status === 'checking_compliance' || status === 'checking_prohibited_practices') {
        setPhase('evaluating')
        pollTimer.current = setTimeout(() => pollUntilReady(id), POLL_INTERVAL_MS)
        return
      }
      if (status === 'failed') {
        // A terminal failure the backend detected (e.g. the remote LLM
        // became unreachable mid-run) -- stop polling and clear the stuck
        // in-flight marker so reloading this page doesn't just resume
        // waiting on a run that already died. See onReset/reset() for the
        // matching "Try again" action.
        localStorage.removeItem(ACTIVE_EVALUATION_KEY)
        setPhase('error')
        setErrorMessage(error || 'Evaluation failed.')
        return
      }
      await resolveOutcome(id, status)
    } catch (err) {
      // A 404 right after upload just means the background extraction job
      // hasn't saved its first checkpoint yet -- id is known-valid (we just
      // got it back from /upload), so keep polling instead of failing.
      if (err.response?.status === 404) {
        pollTimer.current = setTimeout(() => pollUntilReady(id), POLL_INTERVAL_MS)
        return
      }
      setPhase('error')
      setErrorMessage('Lost connection while checking evaluation status.')
    }
  }

  // Resume tracking an in-flight evaluation after navigation/reload instead
  // of showing a blank upload form for an RFP that's still being processed.
  useEffect(() => {
    loadKpis()
    const stored = localStorage.getItem(ACTIVE_EVALUATION_KEY)
    if (!stored) return
    const { rfpId: storedId, startedAt: storedStartedAt } = JSON.parse(stored)
    setRfpId(storedId)
    setStartedAt(storedStartedAt)
    setPhase('evaluating')
    pollUntilReady(storedId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (phase !== 'evaluating' && phase !== 'uploading') return undefined
    const tick = () => setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000))
    tick()
    const interval = setInterval(tick, 1000)
    return () => clearInterval(interval)
  }, [phase, startedAt])

  async function handleFileSubmit(file) {
    setPhase('uploading')
    setErrorMessage('')
    try {
      const { rfp_id } = await uploadRfp(file)
      const now = Date.now()
      setRfpId(rfp_id)
      setStartedAt(now)
      setPhase('evaluating')
      localStorage.setItem(ACTIVE_EVALUATION_KEY, JSON.stringify({ rfpId: rfp_id, startedAt: now }))
      pollUntilReady(rfp_id)
    } catch {
      setPhase('error')
      setErrorMessage('Upload failed. Is the backend running?')
    }
  }

  function reset() {
    stopPolling()
    localStorage.removeItem(ACTIVE_EVALUATION_KEY)
    setPhase('idle')
    setRfpId(null)
    setRecord(null)
    setAllCriteria([])
    setFlaggedCriteria([])
    setErrorMessage('')
    setStartedAt(null)
    setElapsedSeconds(0)
  }

  const publishedCount = myRfps?.filter((r) => r.status !== 'draft').length ?? null
  const openCount = myRfps?.filter((r) => r.status === 'published').length ?? null
  const totalBids = myRfps?.reduce((sum, r) => sum + r.bid_count, 0) ?? null

  return (
    <div className="flex min-h-screen flex-col bg-canvas text-ink">
      <Nav />

      <Container className="flex-1">
        <div className="flex items-center justify-between border-b border-line py-4">
          <div className="flex items-center gap-2 text-sm text-subtle">
            <span className="font-medium text-ink">Buyer</span>
            <ChevronRight size={14} />
            <span>RFP Setup</span>
          </div>
          <StatusPill phase={phase} />
        </div>

        <main className="py-10">
          <h1 className="text-2xl font-semibold text-ink">RFP Setup</h1>
          <p className="mt-1 text-sm text-subtle">
            Upload an RFP/tender PDF. We&apos;ll check it against government procurement norms
            before it&apos;s published.
          </p>

          <div className="mt-6">
            <KpiStrip>
              <KpiCard icon={FileStack} label="My RFPs" value={publishedCount ?? '—'} index={0} />
              <KpiCard icon={ShieldCheck} label="Currently open" value={openCount ?? '—'} index={1} />
              <KpiCard
                icon={Files}
                label="Bids received"
                value={totalBids ?? '—'}
                context="across all your RFPs"
                index={2}
              />
              <KpiCard
                icon={AlertTriangle}
                label="Flagged criteria"
                value={flaggedCount ?? '—'}
                context={myRfps?.length > 20 ? 'across 20 most recent RFPs' : 'across all your RFPs'}
                index={3}
              />
            </KpiStrip>
          </div>

          <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              {phase === 'idle' ? (
                <RfpUploadForm onSubmit={handleFileSubmit} />
              ) : (
                <EvaluationResult
                  phase={phase}
                  rfpId={rfpId}
                  record={record}
                  flaggedCriteria={flaggedCriteria}
                  errorMessage={errorMessage}
                  elapsedLabel={startedAt ? formatElapsed(elapsedSeconds) : null}
                  onReset={reset}
                  onPublishWithOverrides={publishWithOverrides}
                />
              )}
            </div>
            <div className="space-y-6">
              <RecentRfpsCard rfps={myRfps} />
              <CheckpointStepsCard />
            </div>
          </div>
        </main>
      </Container>

      <Footer slim />
    </div>
  )
}
