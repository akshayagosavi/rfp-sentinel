import { useEffect, useState } from 'react'
import { AlertTriangle, BookOpen, CheckCircle2, Loader2, ShieldAlert, Users as UsersIcon, XCircle } from 'lucide-react'
import { getFlaggedRfps, getNorms, getUsers, setUserActive, updateNormStatus } from '../api/client'
import { useAuth } from '../context/AuthContext'
import Nav from '../components/Nav'

const STATUS_META = {
  active: { label: 'Active', className: 'border-success-line bg-success-soft text-success' },
  superseded: { label: 'Superseded', className: 'border-accent/30 bg-accent/10 text-accent' },
  withdrawn: { label: 'Withdrawn', className: 'border-danger-line bg-danger-soft text-danger' },
}

const STATUS_OPTIONS = ['active', 'superseded', 'withdrawn']

function StatusChip({ status }) {
  const meta = STATUS_META[status] ?? STATUS_META.active
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium ${meta.className}`}>
      {meta.label}
    </span>
  )
}

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function NormRow({ norm, onStatusChange }) {
  const [pending, setPending] = useState(norm.status)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  async function handleApply() {
    if (pending === norm.status) return
    setSaving(true)
    setError('')
    setSaved(false)
    try {
      await updateNormStatus(norm.norm_name, pending)
      onStatusChange(norm.norm_name, pending)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch {
      setError('Could not update status.')
      setPending(norm.status)
    } finally {
      setSaving(false)
    }
  }

  return (
    <li className="rounded-card border border-line bg-elevated p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium text-ink">{norm.norm_name}</p>
            <StatusChip status={norm.status} />
          </div>
          <p className="mt-1 text-xs text-subtle">
            {norm.source_file} · {norm.chunk_count} indexed chunks
            {norm.version && ` · v${norm.version}`}
            {norm.effective_date && ` · effective ${formatDate(norm.effective_date)}`}
          </p>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-3">
        <select
          value={pending}
          onChange={(e) => {
            setPending(e.target.value)
            setSaved(false)
          }}
          className="rounded-md border border-line bg-canvas px-3 py-1.5 text-sm text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {STATUS_META[s].label}
            </option>
          ))}
        </select>
        <button
          onClick={handleApply}
          disabled={saving || pending === norm.status}
          className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm font-medium text-ink transition-colors duration-200 hover:border-accent/40 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Apply'}
        </button>
        {saved && (
          <span className="flex items-center gap-1 text-xs text-success">
            <CheckCircle2 size={13} />
            Updated
          </span>
        )}
        {error && <span className="text-xs text-danger">{error}</span>}
      </div>

      {pending !== norm.status && pending !== 'active' && (
        <div className="mt-3 flex gap-2 rounded-md border border-accent/30 bg-accent/5 px-3 py-2 text-xs text-subtle">
          <AlertTriangle size={13} className="mt-0.5 shrink-0 text-accent" />
          <span>
            Marking this {pending} removes it from every future compliance check and evidence search
            immediately. Past evaluations that already cited it stay traceable to the version that was
            active when they ran -- nothing is deleted.
          </span>
        </div>
      )}
    </li>
  )
}

const ROLE_META = {
  buyer: 'border-line bg-surface text-subtle',
  bidder: 'border-line bg-surface text-subtle',
  admin: 'border-accent/30 bg-accent/10 text-accent',
}

function RoleChip({ role }) {
  return (
    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${ROLE_META[role] ?? ROLE_META.buyer}`}>
      {role}
    </span>
  )
}

function UserRow({ user, isSelf, onToggle }) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function handleToggle() {
    setSaving(true)
    setError('')
    try {
      await onToggle(user.id, !user.is_active)
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not update this account.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <li className="rounded-card border border-line bg-elevated p-4">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className="truncate text-sm font-medium text-ink">{user.org_name}</p>
            <RoleChip role={user.role} />
            {!user.is_active && (
              <span className="rounded-full border border-danger-line bg-danger-soft px-2.5 py-0.5 text-xs font-medium text-danger">
                Deactivated
              </span>
            )}
          </div>
          <p className="mt-0.5 truncate text-xs text-subtle">
            {user.email} · joined {formatDate(user.created_at)}
          </p>
        </div>
        {isSelf ? (
          <span className="shrink-0 text-xs text-subtle">This is you</span>
        ) : (
          <button
            onClick={handleToggle}
            disabled={saving}
            className={`shrink-0 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors duration-200 disabled:cursor-not-allowed disabled:opacity-50 ${
              user.is_active
                ? 'border-line bg-surface text-ink hover:border-danger-line hover:text-danger'
                : 'border-line bg-surface text-ink hover:border-accent/40'
            }`}
          >
            {saving ? 'Saving...' : user.is_active ? 'Deactivate' : 'Reactivate'}
          </button>
        )}
      </div>
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </li>
  )
}

// A criterion Checkpoint A flagged (compliance_issue and/or
// prohibited_practice_issue) that made it into a published RFP. Real GeM
// publishing only reaches this state through the frontend's
// publish-with-overrides flow, which requires reasoning for every flagged
// criterion -- but that's a client-side guard, not enforced by the
// backend, so override_reasoning being missing here is a genuine signal
// worth an admin's attention, not just a formatting gap.
function FlaggedCriterionCard({ criterion }) {
  return (
    <li className="rounded-md border border-line bg-canvas p-3">
      <p className="text-xs text-ink">{criterion.text}</p>
      {criterion.compliance_issue && (
        <div className="mt-2 flex gap-2 rounded-md border border-danger-line bg-danger-soft px-3 py-2 text-xs text-danger">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-medium">Compliance issue</p>
            <p className="mt-0.5">{criterion.compliance_issue}</p>
            {criterion.compliance_citation && (
              <p className="mt-1 text-danger/80">
                Norm: {criterion.compliance_citation.norm_name}
                {criterion.compliance_citation.clause_ref && ` · clause ${criterion.compliance_citation.clause_ref}`}
              </p>
            )}
          </div>
        </div>
      )}
      {criterion.prohibited_practice_issue && (
        <div className="mt-2 flex gap-2 rounded-md border border-danger-line bg-danger-soft px-3 py-2 text-xs text-danger">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-medium">Prohibited practice</p>
            <p className="mt-0.5">{criterion.prohibited_practice_issue}</p>
            {criterion.prohibited_practice_citation?.prohibited_practice && (
              <p className="mt-1 text-danger/80">{criterion.prohibited_practice_citation.prohibited_practice}</p>
            )}
          </div>
        </div>
      )}
      {criterion.override_reasoning ? (
        <div className="mt-2 flex gap-2 rounded-md border border-line bg-surface px-3 py-2 text-xs text-subtle">
          <CheckCircle2 size={13} className="mt-0.5 shrink-0 text-success" />
          <div>
            <p className="font-medium text-ink">Buyer&apos;s override reasoning</p>
            <p className="mt-0.5">{criterion.override_reasoning}</p>
          </div>
        </div>
      ) : (
        <div className="mt-2 flex gap-2 rounded-md border border-danger-line bg-danger-soft px-3 py-2 text-xs text-danger">
          <XCircle size={13} className="mt-0.5 shrink-0" />
          <p className="font-medium">No override reasoning recorded for this flag.</p>
        </div>
      )}
    </li>
  )
}

function FlaggedRfpCard({ rfp }) {
  const [expanded, setExpanded] = useState(false)
  const missingReasoningCount = rfp.flagged_criteria.filter((c) => !c.override_reasoning).length

  return (
    <li className="rounded-card border border-line bg-elevated p-5">
      <button onClick={() => setExpanded((e) => !e)} className="flex w-full items-start justify-between gap-4 text-left">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-ink">{rfp.title}</p>
          <p className="mt-0.5 text-xs text-subtle">
            {rfp.buyer_org} · {rfp.flagged_criteria.length} flagged criterion/criteria · status: {rfp.status}
          </p>
        </div>
        {missingReasoningCount > 0 && (
          <span className="flex shrink-0 items-center gap-1 rounded-full border border-danger-line bg-danger-soft px-2.5 py-0.5 text-xs font-medium text-danger">
            <ShieldAlert size={11} />
            {missingReasoningCount} unjustified
          </span>
        )}
      </button>
      {expanded && (
        <ul className="mt-4 space-y-2">
          {rfp.flagged_criteria.map((c) => (
            <FlaggedCriterionCard key={c.id} criterion={c} />
          ))}
        </ul>
      )}
    </li>
  )
}

export default function AdminDashboard() {
  const { user: currentUser } = useAuth()
  const [norms, setNorms] = useState(null)
  const [error, setError] = useState('')
  const [users, setUsers] = useState(null)
  const [usersError, setUsersError] = useState('')
  const [flaggedRfps, setFlaggedRfps] = useState(null)
  const [flaggedError, setFlaggedError] = useState('')

  useEffect(() => {
    getNorms()
      .then(setNorms)
      .catch(() => setError('Could not load norms. Is the backend running?'))
    getUsers()
      .then(setUsers)
      .catch(() => setUsersError('Could not load users. Is the backend running?'))
    getFlaggedRfps()
      .then(setFlaggedRfps)
      .catch(() => setFlaggedError('Could not load flagged RFPs. Is the backend running?'))
  }, [])

  function handleStatusChange(normName, newStatus) {
    setNorms((prev) => prev.map((n) => (n.norm_name === normName ? { ...n, status: newStatus } : n)))
  }

  async function handleUserToggle(userId, isActive) {
    await setUserActive(userId, isActive)
    setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, is_active: isActive } : u)))
  }

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <Nav />

      <div className="mx-auto max-w-3xl px-6">
        <main className="py-10">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-accent/10 text-accent">
              <BookOpen size={22} />
            </span>
            <div>
              <h1 className="text-xl font-semibold text-ink">Norm Knowledge Base</h1>
              <p className="text-sm text-subtle">
                Every RFP compliance check and bid evidence search only ever looks at norms marked Active.
              </p>
            </div>
          </div>

          <div className="mt-8">
            {error && (
              <p className="rounded-md border border-danger-line bg-danger-soft px-4 py-3 text-sm text-danger">
                {error}
              </p>
            )}

            {!error && norms === null && (
              <div className="flex items-center gap-2 text-sm text-subtle">
                <Loader2 size={16} className="animate-spin" />
                Loading...
              </div>
            )}

            {norms?.length === 0 && (
              <p className="rounded-md border border-line bg-elevated px-4 py-6 text-center text-sm text-subtle">
                No norms have been ingested yet.
              </p>
            )}

            {norms?.length > 0 && (
              <ul className="space-y-3">
                {norms.map((norm) => (
                  <NormRow key={norm.norm_name} norm={norm} onStatusChange={handleStatusChange} />
                ))}
              </ul>
            )}
          </div>

          <div className="mt-12 flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-accent/10 text-accent">
              <UsersIcon size={22} />
            </span>
            <div>
              <h1 className="text-xl font-semibold text-ink">Users</h1>
              <p className="text-sm text-subtle">
                Deactivating suspends login access -- it never deletes an account or touches anything
                they&apos;ve already published or submitted.
              </p>
            </div>
          </div>

          <div className="mt-8">
            {usersError && (
              <p className="rounded-md border border-danger-line bg-danger-soft px-4 py-3 text-sm text-danger">
                {usersError}
              </p>
            )}

            {!usersError && users === null && (
              <div className="flex items-center gap-2 text-sm text-subtle">
                <Loader2 size={16} className="animate-spin" />
                Loading...
              </div>
            )}

            {users?.length > 0 && (
              <ul className="space-y-3">
                {users.map((u) => (
                  <UserRow key={u.id} user={u} isSelf={u.email === currentUser?.email} onToggle={handleUserToggle} />
                ))}
              </ul>
            )}
          </div>

          <div className="mt-12 flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-accent/10 text-accent">
              <ShieldAlert size={22} />
            </span>
            <div>
              <h1 className="text-xl font-semibold text-ink">Buyer Conduct Oversight</h1>
              <p className="text-sm text-subtle">
                Published RFPs with at least one criterion Checkpoint A flagged, and whether the buyer
                recorded a reason for publishing anyway.
              </p>
            </div>
          </div>

          <div className="mt-8">
            {flaggedError && (
              <p className="rounded-md border border-danger-line bg-danger-soft px-4 py-3 text-sm text-danger">
                {flaggedError}
              </p>
            )}

            {!flaggedError && flaggedRfps === null && (
              <div className="flex items-center gap-2 text-sm text-subtle">
                <Loader2 size={16} className="animate-spin" />
                Loading...
              </div>
            )}

            {flaggedRfps?.length === 0 && (
              <p className="rounded-md border border-line bg-elevated px-4 py-6 text-center text-sm text-subtle">
                No published RFP currently has a flagged criterion.
              </p>
            )}

            {flaggedRfps?.length > 0 && (
              <ul className="space-y-3">
                {flaggedRfps.map((rfp) => (
                  <FlaggedRfpCard key={rfp.rfp_id} rfp={rfp} />
                ))}
              </ul>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
