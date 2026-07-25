import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BadgeCheck, ChevronLeft, KeyRound, UploadCloud, UserCircle2 } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { changePassword, updateProfile, uploadMiiCertificate, uploadMseCertificate } from '../api/client'
import Nav from '../components/Nav'

const DASHBOARD_PATH = { buyer: '/buyer/dashboard', bidder: '/bidder/dashboard', admin: '/admin/dashboard' }

// MSE/MII are seller-level GeM registration attributes, proven once by an
// uploaded certificate here on the profile -- not re-declared per bid (see
// backend/api/auth.py module docstring for why).
function CertificateSlot({ label, isCertified, filename, uploading, onUpload }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-line bg-canvas px-4 py-3">
      <div className="min-w-0">
        <p className="text-sm font-medium text-ink">{label}</p>
        {isCertified ? (
          <p className="mt-0.5 flex items-center gap-1 truncate text-xs text-success">
            <BadgeCheck size={12} />
            Certified -- {filename}
          </p>
        ) : (
          <p className="mt-0.5 text-xs text-subtle">Not certified. Upload proof to declare.</p>
        )}
      </div>
      <label className="flex shrink-0 cursor-pointer items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 text-xs font-medium text-accent transition-colors duration-200 hover:border-accent/40">
        <UploadCloud size={12} />
        {uploading ? 'Uploading...' : isCertified ? 'Replace' : 'Upload'}
        <input
          type="file"
          accept="application/pdf"
          className="hidden"
          disabled={uploading}
          onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])}
        />
      </label>
    </div>
  )
}

export default function Profile() {
  const { role, user, refreshUser } = useAuth()
  const [orgName, setOrgName] = useState('')
  const [gemSellerProof, setGemSellerProof] = useState('')
  const [profileSaving, setProfileSaving] = useState(false)
  const [profileMessage, setProfileMessage] = useState('')

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [passwordSaving, setPasswordSaving] = useState(false)
  const [passwordMessage, setPasswordMessage] = useState('')
  const [passwordError, setPasswordError] = useState('')

  const [uploadingMse, setUploadingMse] = useState(false)
  const [uploadingMii, setUploadingMii] = useState(false)
  const [certError, setCertError] = useState('')

  useEffect(() => {
    if (user) {
      setOrgName(user.org_name ?? '')
      setGemSellerProof(user.gem_seller_proof ?? '')
    }
  }, [user])

  async function handleProfileSave(e) {
    e.preventDefault()
    setProfileSaving(true)
    setProfileMessage('')
    try {
      await updateProfile(orgName, gemSellerProof)
      await refreshUser()
      setProfileMessage('Saved.')
    } catch {
      setProfileMessage('Could not save changes.')
    } finally {
      setProfileSaving(false)
    }
  }

  async function handleMseUpload(file) {
    setUploadingMse(true)
    setCertError('')
    try {
      await uploadMseCertificate(file)
      await refreshUser()
    } catch {
      setCertError('Could not upload MSE certificate.')
    } finally {
      setUploadingMse(false)
    }
  }

  async function handleMiiUpload(file) {
    setUploadingMii(true)
    setCertError('')
    try {
      await uploadMiiCertificate(file)
      await refreshUser()
    } catch {
      setCertError('Could not upload MII certificate.')
    } finally {
      setUploadingMii(false)
    }
  }

  async function handlePasswordChange(e) {
    e.preventDefault()
    setPasswordSaving(true)
    setPasswordMessage('')
    setPasswordError('')
    try {
      await changePassword(currentPassword, newPassword)
      setPasswordMessage('Password changed.')
      setCurrentPassword('')
      setNewPassword('')
    } catch (err) {
      setPasswordError(err.response?.status === 401 ? 'Current password is incorrect.' : 'Could not change password.')
    } finally {
      setPasswordSaving(false)
    }
  }

  return (
    <div className="min-h-screen bg-canvas text-ink">
      <Nav />

      <div className="mx-auto max-w-2xl px-6">
        <div className="border-b border-line py-4">
          <Link
            to={DASHBOARD_PATH[role] ?? '/'}
            className="flex items-center gap-1 text-sm text-subtle hover:text-ink"
          >
            <ChevronLeft size={14} />
            Dashboard
          </Link>
        </div>

        <main className="py-10">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-accent/10 text-accent">
              <UserCircle2 size={22} />
            </span>
            <div>
              <h1 className="text-xl font-semibold text-ink">Profile</h1>
              <p className="text-sm text-subtle">{user?.email}</p>
            </div>
          </div>

          <form onSubmit={handleProfileSave} className="mt-8 space-y-4 rounded-card border border-line bg-elevated p-6">
            <h2 className="text-sm font-semibold text-ink">Account details</h2>
            <div>
              <label htmlFor="orgName" className="block text-sm font-medium text-ink">
                {role === 'buyer' ? 'Organization name' : 'Company / seller name'}
              </label>
              <input
                id="orgName"
                type="text"
                required
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                className="mt-1 w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink transition-colors duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
              />
            </div>
            {role === 'bidder' && (
              <div>
                <label htmlFor="gemSellerProof" className="block text-sm font-medium text-ink">
                  GeM Seller ID <span className="font-normal text-subtle">(not verified yet)</span>
                </label>
                <input
                  id="gemSellerProof"
                  type="text"
                  value={gemSellerProof}
                  onChange={(e) => setGemSellerProof(e.target.value)}
                  className="mt-1 w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink transition-colors duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
                />
              </div>
            )}
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={profileSaving}
                className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white transition-all duration-200 hover:scale-[1.01] hover:bg-accent-hover disabled:opacity-60"
              >
                {profileSaving ? 'Saving...' : 'Save changes'}
              </button>
              {profileMessage && <span className="text-xs text-subtle">{profileMessage}</span>}
            </div>
          </form>

          {role === 'bidder' && (
            <div className="mt-6 space-y-4 rounded-card border border-line bg-elevated p-6">
              <div>
                <h2 className="text-sm font-semibold text-ink">MSE / MII certification</h2>
                <p className="mt-1 text-xs text-subtle">
                  Declared once here, at the account level, matching how GeM verifies seller status --
                  not re-asked on every bid you submit.
                </p>
              </div>
              <CertificateSlot
                label="Micro or Small Enterprise (MSE) -- Udyam Registration"
                isCertified={user?.is_mse}
                filename={user?.mse_certificate_filename}
                uploading={uploadingMse}
                onUpload={handleMseUpload}
              />
              <CertificateSlot
                label="Class-I/II Local Supplier (Make in India)"
                isCertified={user?.is_mii_local}
                filename={user?.mii_certificate_filename}
                uploading={uploadingMii}
                onUpload={handleMiiUpload}
              />
              {certError && (
                <p className="rounded-md border border-danger-line bg-danger-soft px-3 py-2 text-sm text-danger">
                  {certError}
                </p>
              )}
            </div>
          )}

          <form onSubmit={handlePasswordChange} className="mt-6 space-y-4 rounded-card border border-line bg-elevated p-6">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
              <KeyRound size={15} className="text-accent" />
              Change password
            </h2>
            <div>
              <label htmlFor="currentPassword" className="block text-sm font-medium text-ink">
                Current password
              </label>
              <input
                id="currentPassword"
                type="password"
                required
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className="mt-1 w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink transition-colors duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
              />
            </div>
            <div>
              <label htmlFor="newPassword" className="block text-sm font-medium text-ink">
                New password
              </label>
              <input
                id="newPassword"
                type="password"
                required
                minLength={8}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="mt-1 w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink transition-colors duration-200 focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
              />
            </div>
            {passwordError && (
              <p className="rounded-md border border-danger-line bg-danger-soft px-3 py-2 text-sm text-danger">
                {passwordError}
              </p>
            )}
            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={passwordSaving}
                className="rounded-md border border-line bg-surface px-4 py-2 text-sm font-medium text-ink transition-colors duration-200 hover:border-accent/40 disabled:opacity-60"
              >
                {passwordSaving ? 'Changing...' : 'Change password'}
              </button>
              {passwordMessage && <span className="text-xs text-subtle">{passwordMessage}</span>}
            </div>
          </form>
        </main>
      </div>
    </div>
  )
}
