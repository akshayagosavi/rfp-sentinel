import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  FileStack,
  Loader2,
  ShieldAlert,
  ShieldCheck,
  Upload,
  UserPlus,
  Users as UsersIcon,
  XCircle,
} from 'lucide-react'
import {
  createBuyer,
  getBids,
  getFlaggedRfps,
  getNorms,
  getUsers,
  setUserActive,
  updateNormStatus,
  uploadNorm,
} from '../api/client'
import { useAuth } from '../context/AuthContext'
import Nav from '../components/Nav'
import Container from '../components/Container'
import Footer from '../components/Footer'
import { KpiCard, KpiStrip } from '../components/KpiStrip'

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

// Adds a brand-new norm document to the knowledge base -- previously the
// only way to do this at all was hand-editing manifest.json and running
// the CLI ingestion script directly. Ingestion runs synchronously on the
// backend (no background-task/polling infra exists for this yet, unlike
// RFP upload), so this can take 1-2 minutes for a real document -- the
// button's own label says so, rather than looking stuck.
function UploadNormForm({ onUploaded }) {
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState(null)
  const [normName, setNormName] = useState('')
  const [version, setVersion] = useState('')
  const [effectiveDate, setEffectiveDate] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    if (!file) {
      setError('Choose a PDF file first.')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const result = await uploadNorm(file, normName.trim(), version.trim(), effectiveDate.trim())
      setFile(null)
      setNormName('')
      setVersion('')
      setEffectiveDate('')
      setOpen(false)
      onUploaded(result)
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not ingest this document.')
    } finally {
      setSubmitting(false)
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 rounded-md bg-accent px-3 py-2 text-xs font-medium text-white transition-all duration-200 hover:scale-[1.01] hover:bg-accent-hover"
      >
        <Upload size={14} />
        Add a norm document
      </button>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-card border border-line bg-elevated p-4 sm:max-w-md">
      <p className="text-sm font-medium text-ink">Upload a new norm document</p>
      <div className="mt-3 space-y-2">
        <input
          type="text"
          required
          value={normName}
          onChange={(e) => setNormName(e.target.value)}
          placeholder="Norm name (e.g. GFR 2017 Chapter 6)"
          className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink transition-colors duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
        />
        <div className="flex gap-2">
          <input
            type="text"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
            placeholder="Version (optional)"
            className="w-1/2 rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink transition-colors duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
          />
          <input
            type="date"
            value={effectiveDate}
            onChange={(e) => setEffectiveDate(e.target.value)}
            className="w-1/2 rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink transition-colors duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
          />
        </div>
        <input
          type="file"
          accept="application/pdf"
          required
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="w-full text-sm text-ink file:mr-3 file:rounded-md file:border file:border-line file:bg-surface file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-ink"
        />
      </div>
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
      <div className="mt-3 flex items-center gap-2">
        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-accent px-4 py-2 text-xs font-medium text-white transition-all duration-200 hover:scale-[1.01] hover:bg-accent-hover disabled:opacity-60"
        >
          {submitting ? 'Ingesting (can take 1-2 min)...' : 'Upload & ingest'}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          disabled={submitting}
          className="text-xs font-medium text-subtle hover:text-ink disabled:opacity-50"
        >
          Cancel
        </button>
      </div>
    </form>
  )
}

function NormCard({ norm, onStatusChange }) {
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
    <div className="flex h-full flex-col rounded-card border border-line bg-elevated p-5">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-ink">{norm.norm_name}</p>
        <StatusChip status={norm.status} />
      </div>
      <p className="mt-1 text-xs text-subtle">
        {norm.source_file} · {norm.chunk_count} indexed chunks
        {norm.version && ` · v${norm.version}`}
        {norm.effective_date && ` · effective ${formatDate(norm.effective_date)}`}
      </p>

      <div className="mt-auto pt-4">
        <div className="flex items-center gap-2">
          <select
            value={pending}
            onChange={(e) => {
              setPending(e.target.value)
              setSaved(false)
            }}
            className="min-w-0 flex-1 rounded-md border border-line bg-canvas px-2.5 py-1.5 text-xs text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
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
            className="shrink-0 rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink transition-colors duration-200 hover:border-accent/40 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Apply'}
          </button>
        </div>
        {saved && (
          <span className="mt-2 flex items-center gap-1 text-xs text-success">
            <CheckCircle2 size={13} />
            Updated
          </span>
        )}
        {error && <span className="mt-2 block text-xs text-danger">{error}</span>}
        {pending !== norm.status && pending !== 'active' && (
          <div className="mt-3 flex gap-2 rounded-md border border-accent/30 bg-accent/5 px-3 py-2 text-xs text-subtle">
            <AlertTriangle size={13} className="mt-0.5 shrink-0 text-accent" />
            <span>Removes it from every future compliance check and evidence search immediately.</span>
          </div>
        )}
      </div>
    </div>
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

// Buyers don't get open self-signup like bidders do -- a buyer account
// represents an authorized government department, provisioned by an
// admin, not claimed by whoever registers. Previously the only buyer
// account that could ever exist was the one seeded demo account; this is
// the fix for that real limitation.
function CreateBuyerForm({ onCreated }) {
  const [open, setOpen] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [orgName, setOrgName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await createBuyer(email.trim(), password, orgName.trim())
      setEmail('')
      setPassword('')
      setOrgName('')
      setOpen(false)
      onCreated()
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not create this buyer account.')
    } finally {
      setSubmitting(false)
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 rounded-md bg-accent px-3 py-2 text-xs font-medium text-white transition-all duration-200 hover:scale-[1.01] hover:bg-accent-hover"
      >
        <UserPlus size={14} />
        Create buyer account
      </button>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="rounded-card border border-line bg-elevated p-4 sm:max-w-md">
      <p className="text-sm font-medium text-ink">New buyer account</p>
      <div className="mt-3 space-y-2">
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email"
          className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink transition-colors duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
        />
        <input
          type="text"
          required
          value={orgName}
          onChange={(e) => setOrgName(e.target.value)}
          placeholder="Department / organization name"
          className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink transition-colors duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
        />
        <input
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink transition-colors duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
        />
      </div>
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
      <div className="mt-3 flex items-center gap-2">
        <button
          type="submit"
          disabled={submitting}
          className="rounded-md bg-accent px-4 py-2 text-xs font-medium text-white transition-all duration-200 hover:scale-[1.01] hover:bg-accent-hover disabled:opacity-60"
        >
          {submitting ? 'Creating...' : 'Create account'}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="text-xs font-medium text-subtle hover:text-ink"
        >
          Cancel
        </button>
      </div>
    </form>
  )
}

function UserCard({ user, isSelf, onToggle }) {
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
    <div className="rounded-card border border-line bg-elevated p-4">
      <div className="flex items-center gap-2">
        <p className="truncate text-sm font-medium text-ink">{user.org_name}</p>
        <RoleChip role={user.role} />
      </div>
      <p className="mt-0.5 truncate text-xs text-subtle">
        {user.email} · joined {formatDate(user.created_at)}
      </p>
      <div className="mt-3 flex items-center justify-between gap-2">
        {!user.is_active ? (
          <span className="rounded-full border border-danger-line bg-danger-soft px-2.5 py-0.5 text-xs font-medium text-danger">
            Deactivated
          </span>
        ) : (
          <span className="rounded-full border border-success-line bg-success-soft px-2.5 py-0.5 text-xs font-medium text-success">
            Active
          </span>
        )}
        {isSelf ? (
          <span className="text-xs text-subtle">This is you</span>
        ) : (
          <button
            onClick={handleToggle}
            disabled={saving}
            className="rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink transition-colors duration-200 hover:border-accent/40 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? 'Saving...' : user.is_active ? 'Deactivate' : 'Reactivate'}
          </button>
        )}
      </div>
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </div>
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

const TABS = [
  { id: 'norms', label: 'Norm Knowledge Base', icon: BookOpen },
  { id: 'users', label: 'Users', icon: UsersIcon },
  { id: 'conduct', label: 'Buyer Conduct Oversight', icon: ShieldAlert },
]

export default function AdminDashboard() {
  const { user: currentUser } = useAuth()
  const [tab, setTab] = useState('norms')

  const [norms, setNorms] = useState(null)
  const [error, setError] = useState('')
  const [users, setUsers] = useState(null)
  const [usersError, setUsersError] = useState('')
  const [flaggedRfps, setFlaggedRfps] = useState(null)
  const [flaggedError, setFlaggedError] = useState('')
  const [publishedCount, setPublishedCount] = useState(null)

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
    // Reuses the public bid-listing endpoint (same one Bids.jsx calls) for
    // an honest "Published RFPs" count -- admin has no dedicated "all RFPs"
    // endpoint, and this is real data, not a fabricated number.
    getBids()
      .then((bids) => setPublishedCount(bids.length))
      .catch(() => setPublishedCount(null))
  }, [])

  function handleStatusChange(normName, newStatus) {
    setNorms((prev) => prev.map((n) => (n.norm_name === normName ? { ...n, status: newStatus } : n)))
  }

  function refreshNorms() {
    getNorms()
      .then(setNorms)
      .catch(() => setError('Could not load norms. Is the backend running?'))
  }

  async function handleUserToggle(userId, isActive) {
    await setUserActive(userId, isActive)
    setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, is_active: isActive } : u)))
  }

  function refreshUsers() {
    getUsers()
      .then(setUsers)
      .catch(() => setUsersError('Could not load users. Is the backend running?'))
  }

  const activeNormsCount = norms?.filter((n) => n.status === 'active').length ?? null

  return (
    <div className="flex min-h-screen flex-col bg-canvas text-ink">
      <Nav />

      <Container className="flex-1">
        <main className="py-10">
          <h1 className="text-2xl font-semibold text-ink">Admin</h1>
          <p className="mt-1 text-sm text-subtle">Norm knowledge base, user accounts, and buyer-conduct oversight.</p>

          <div className="mt-6">
            <KpiStrip>
              <KpiCard icon={ShieldCheck} label="Active norms" value={activeNormsCount ?? '—'} index={0} />
              <KpiCard icon={UsersIcon} label="Total users" value={users?.length ?? '—'} index={1} />
              <KpiCard
                icon={FileStack}
                label="Published RFPs"
                value={publishedCount ?? '—'}
                context="via the public listing"
                index={2}
              />
              <KpiCard icon={ShieldAlert} label="Flagged RFPs" value={flaggedRfps?.length ?? '—'} index={3} />
            </KpiStrip>
          </div>

          <div className="mt-8 flex gap-1 overflow-x-auto rounded-md border border-line bg-elevated p-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`flex shrink-0 items-center gap-1.5 rounded-md px-3 py-2 text-xs font-medium transition-colors duration-200 ${
                  tab === t.id ? 'bg-accent text-white' : 'text-subtle hover:text-ink'
                }`}
              >
                <t.icon size={14} />
                {t.label}
              </button>
            ))}
          </div>

          {tab === 'norms' && (
            <div className="mt-6">
              <p className="text-xs text-subtle">
                Every RFP compliance check and bid evidence search only ever looks at norms marked Active.
              </p>

              <div className="mt-4">
                <UploadNormForm onUploaded={refreshNorms} />
              </div>

              <div className="mt-4">
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
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                    {norms.map((norm) => (
                      <NormCard key={norm.norm_name} norm={norm} onStatusChange={handleStatusChange} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {tab === 'users' && (
            <div className="mt-6">
              <p className="text-xs text-subtle">
                Deactivating suspends login access immediately -- it never deletes an account or touches
                anything they&apos;ve already published or submitted.
              </p>

              <div className="mt-4">
                <CreateBuyerForm onCreated={refreshUsers} />
              </div>

              <div className="mt-4">
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
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                    {users.map((u) => (
                      <UserCard key={u.id} user={u} isSelf={u.email === currentUser?.email} onToggle={handleUserToggle} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {tab === 'conduct' && (
            <div className="mt-6">
              <p className="text-xs text-subtle">
                Published RFPs with at least one criterion Checkpoint A flagged, and whether the buyer
                recorded a reason for publishing anyway.
              </p>

              <div className="mt-4">
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
            </div>
          )}
        </main>
      </Container>

      <Footer slim />
    </div>
  )
}
