import { useState } from 'react'
import { Link } from 'react-router-dom'
import { motion, useReducedMotion } from 'framer-motion'
import { CheckCircle2, AlertTriangle, XCircle, Loader2 } from 'lucide-react'

export default function EvaluationResult({
  phase,
  rfpId,
  record,
  flaggedCriteria,
  errorMessage,
  elapsedLabel,
  onReset,
  onPublishWithOverrides,
}) {
  const reduceMotion = useReducedMotion()
  const [reasoningById, setReasoningById] = useState({})
  const [publishing, setPublishing] = useState(false)
  const fadeIn = {
    initial: reduceMotion ? undefined : { opacity: 0, y: 8 },
    animate: reduceMotion ? undefined : { opacity: 1, y: 0 },
    transition: { duration: 0.3, ease: 'easeOut' },
  }

  if (phase === 'uploading' || phase === 'evaluating') {
    return (
      <motion.div {...fadeIn} className="rounded-card border border-line bg-elevated px-6 py-12 text-center">
        <Loader2 size={24} className="mx-auto animate-spin text-accent" />
        <p className="mt-4 text-sm text-subtle">
          {phase === 'uploading'
            ? 'Uploading...'
            : 'Evaluating against government procurement norms and GeM\'s own RFP guidelines.'}
        </p>
        {phase === 'evaluating' && (
          <p className="mt-1 text-xs text-subtle">
            Typically 8-15 minutes for a full RFP.
            {elapsedLabel && <> Elapsed: {elapsedLabel}.</>}
          </p>
        )}
        {rfpId && <p className="mt-1 text-xs text-subtle/70">RFP ID: {rfpId}</p>}
        <div className="mx-auto mt-6 max-w-xs space-y-2">
          <div className="h-2 animate-pulse rounded-full bg-surface" />
          <div className="h-2 w-4/5 animate-pulse rounded-full bg-surface" />
          <div className="h-2 w-3/5 animate-pulse rounded-full bg-surface" />
        </div>
      </motion.div>
    )
  }

  if (phase === 'success') {
    return (
      <motion.div
        {...fadeIn}
        className="rounded-card border border-success-line bg-success-soft px-6 py-8"
      >
        <div className="flex items-center gap-2">
          <CheckCircle2 size={18} className="text-success" />
          <h2 className="text-sm font-semibold text-success">RFP published successfully and stored.</h2>
        </div>
        <dl className="mt-4 space-y-1 text-sm text-ink">
          <div className="flex gap-2">
            <dt className="font-medium text-subtle">RFP ID:</dt>
            <dd>{record?.rfpId}</dd>
          </div>
          <div className="flex gap-2">
            <dt className="font-medium text-subtle">Criteria evaluated:</dt>
            <dd>{record?.criteriaCount}</dd>
          </div>
          {record?.overriddenCount > 0 && (
            <div className="flex gap-2">
              <dt className="font-medium text-subtle">Published with overrides:</dt>
              <dd>{record.overriddenCount} criterion/criteria, reviewer-justified</dd>
            </div>
          )}
        </dl>
        <div className="mt-6 flex items-center gap-4">
          <Link
            to={`/buyer/rfp/${record?.rfpId}`}
            className="text-sm font-medium text-success underline decoration-success/40 underline-offset-2 transition-colors hover:decoration-success"
          >
            Manage this RFP
          </Link>
          <button
            onClick={onReset}
            className="text-sm font-medium text-success underline decoration-success/40 underline-offset-2 transition-colors hover:decoration-success"
          >
            Upload another RFP
          </button>
        </div>
      </motion.div>
    )
  }

  if (phase === 'invalid') {
    const allJustified = flaggedCriteria.every((c) => (reasoningById[c.id] ?? '').trim().length > 0)

    async function handlePublishAnyway() {
      setPublishing(true)
      try {
        await onPublishWithOverrides(reasoningById)
      } finally {
        setPublishing(false)
      }
    }

    return (
      <motion.div {...fadeIn} className="rounded-card border border-danger-line bg-danger-soft px-6 py-8">
        <div className="flex items-center gap-2">
          <AlertTriangle size={18} className="text-danger" />
          <h2 className="text-sm font-semibold text-danger">
            This RFP has {flaggedCriteria.length} criteria that need attention.
          </h2>
        </div>
        <p className="mt-1 text-xs text-subtle">
          If you've reviewed a flag and disagree, explain why below to override it and publish anyway --
          your reasoning is stored as part of the record.
        </p>
        <ul className="mt-4 space-y-3">
          {flaggedCriteria.map((c) => (
            <li key={c.id} className="rounded-md border border-danger-line bg-elevated px-4 py-3">
              <p className="text-sm font-medium text-ink">{c.text}</p>
              {c.compliance_issue && (
                <div className="mt-2">
                  <span className="text-xs font-medium uppercase tracking-wide text-subtle">
                    Norm conflict
                  </span>
                  <p className="mt-0.5 text-sm text-danger">{c.compliance_issue}</p>
                  {c.compliance_citation && (
                    <p className="mt-1 text-xs text-subtle">
                      Citation: {c.compliance_citation.norm_name}
                      {c.compliance_citation.clause_ref ? `, clause ${c.compliance_citation.clause_ref}` : ''}
                      {c.compliance_citation.page_number ? `, page ${c.compliance_citation.page_number}` : ''}
                    </p>
                  )}
                </div>
              )}
              {c.prohibited_practice_issue && (
                <div className="mt-2">
                  <span className="text-xs font-medium uppercase tracking-wide text-subtle">
                    RFP self-check
                  </span>
                  <p className="mt-0.5 text-sm text-danger">{c.prohibited_practice_issue}</p>
                  {c.prohibited_practice_citation && (
                    <p className="mt-1 text-xs text-subtle">
                      Matches GeM&apos;s own prohibited-practice list: &quot;
                      {c.prohibited_practice_citation.prohibited_practice}&quot;
                    </p>
                  )}
                </div>
              )}
              <textarea
                value={reasoningById[c.id] ?? ''}
                onChange={(e) => setReasoningById((prev) => ({ ...prev, [c.id]: e.target.value }))}
                placeholder="Your reasoning for overriding this flag..."
                rows={2}
                className="mt-2 w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink transition-colors duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
              />
            </li>
          ))}
        </ul>
        <div className="mt-6 flex flex-wrap items-center gap-4">
          <button
            onClick={handlePublishAnyway}
            disabled={!allJustified || publishing}
            className={`rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 ${
              allJustified && !publishing
                ? 'bg-accent text-white hover:scale-[1.01] hover:bg-accent-hover'
                : 'cursor-not-allowed border border-line bg-surface text-subtle'
            }`}
          >
            {publishing ? 'Publishing...' : 'Publish anyway'}
          </button>
          <button
            onClick={onReset}
            className="text-sm font-medium text-danger underline decoration-danger/40 underline-offset-2 transition-colors hover:decoration-danger"
          >
            Upload a revised RFP instead
          </button>
        </div>
      </motion.div>
    )
  }

  return (
    <motion.div {...fadeIn} className="rounded-card border border-danger-line bg-danger-soft px-6 py-8">
      <div className="flex items-center gap-2">
        <XCircle size={18} className="text-danger" />
        <h2 className="text-sm font-semibold text-danger">Something went wrong.</h2>
      </div>
      <p className="mt-1 text-sm text-danger">{errorMessage}</p>
      <button
        onClick={onReset}
        className="mt-6 text-sm font-medium text-danger underline decoration-danger/40 underline-offset-2 transition-colors hover:decoration-danger"
      >
        Try again
      </button>
    </motion.div>
  )
}
