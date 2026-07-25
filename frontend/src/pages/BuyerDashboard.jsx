import { useEffect, useRef, useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { uploadRfp, getStatus, getCriteria, approveCriteria } from '../api/client'
import RfpUploadForm from '../components/RfpUploadForm'
import EvaluationResult from '../components/EvaluationResult'
import Nav from '../components/Nav'

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

export default function BuyerDashboard() {
  const { logout } = useAuth()
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
  }

  async function pollUntilReady(id) {
    try {
      const { status } = await getStatus(id)
      if (status === 'extracting' || status === 'checking_compliance' || status === 'checking_prohibited_practices') {
        setPhase('evaluating')
        pollTimer.current = setTimeout(() => pollUntilReady(id), POLL_INTERVAL_MS)
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

          <div className="mt-8">
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
        </main>
      </div>
    </div>
  )
}
