import axios from 'axios'

// Resolves against whatever host the browser used to load the page (e.g.
// localhost for you, your LAN IP for a teammate), instead of a hardcoded
// 127.0.0.1 -- which only ever means "this same machine," not yours.
const BASE_URL = `http://${window.location.hostname}:8000`

const client = axios.create({
  baseURL: BASE_URL,
})

// v1: token lives in localStorage -- simplest option for a single-machine,
// local-first demo. Trade-off (XSS exposure) is acceptable for now, same
// shortcut spirit as the rest of v1's auth (see backend/auth.py).
const TOKEN_KEY = 'rfp_sentinel_token'

client.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export async function login(email, password) {
  const { data } = await client.post('/auth/login', { email, password })
  return { accessToken: data.access_token, role: data.role }
}

export async function signupBidder(email, password, orgName, gemSellerProof) {
  const { data } = await client.post('/auth/signup/bidder', {
    email,
    password,
    org_name: orgName,
    gem_seller_proof: gemSellerProof || null,
  })
  return { accessToken: data.access_token, role: data.role }
}

export async function getMe() {
  const { data } = await client.get('/auth/me')
  return data
}

export async function updateProfile(orgName, gemSellerProof) {
  const { data } = await client.patch('/auth/me', { org_name: orgName, gem_seller_proof: gemSellerProof || null })
  return data
}

export async function changePassword(currentPassword, newPassword) {
  const { data } = await client.post('/auth/me/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  })
  return data
}

export async function uploadMseCertificate(file) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await client.post('/auth/me/mse-certificate', form)
  return data
}

export async function uploadMiiCertificate(file) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await client.post('/auth/me/mii-certificate', form)
  return data
}

// Public -- no auth required, matches the real-GeM-style "anyone can
// browse published tenders" behavior. Only "Apply" needs an account.
export async function getBids({ keyword, category, status } = {}) {
  const { data } = await client.get('/bids', { params: { keyword, category, status } })
  return data.bids
}

export async function getBidDetail(rfpId) {
  const { data } = await client.get(`/bids/${rfpId}`)
  return data
}

export function bidDocumentUrl(rfpId) {
  return `${BASE_URL}/bids/${rfpId}/document`
}

export async function getLegitimacyCheck(rfpId) {
  const { data } = await client.get(`/bids/${rfpId}/legitimacy-check`)
  return data.citations
}

export async function getRfpSummary(rfpId) {
  const { data } = await client.get(`/bids/${rfpId}/summary`)
  return data.summary
}

// Auth required -- a signed-in bidder's own submitted bids and their status.
export async function getMyBids() {
  const { data } = await client.get('/bidder/my-bids')
  return data.bids
}

export async function submitBid(rfpId, files, financialDocument) {
  const form = new FormData()
  for (const file of files) form.append('files', file)
  form.append('financial_document', financialDocument)
  const { data } = await client.post(`/bidder/bids/${rfpId}/submit`, form)
  return data
}

export async function flagRfp(rfpId, message) {
  const { data } = await client.post(`/bidder/rfps/${rfpId}/flag`, { message })
  return data
}

export async function getRfpFlags(rfpId) {
  const { data } = await client.get(`/rfp/${rfpId}/flags`)
  return data.flags
}

export async function resolveRfpFlag(rfpId, flagId, resolutionNote) {
  const { data } = await client.post(`/rfp/${rfpId}/flags/${flagId}/resolve`, { resolution_note: resolutionNote })
  return data
}

export async function uploadRfp(file) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await client.post('/rfp/upload', form)
  return data
}

export async function getStatus(rfpId) {
  const { data } = await client.get(`/rfp/${rfpId}/status`)
  return data
}

export async function getCriteria(rfpId) {
  const { data } = await client.get(`/rfp/${rfpId}/criteria`)
  return data
}

export async function approveCriteria(rfpId, criteria) {
  const { data } = await client.post(`/rfp/${rfpId}/criteria/approve`, { criteria })
  return data
}

export async function getMyRfps() {
  const { data } = await client.get('/rfp/mine')
  return data.rfps
}

export async function closeRfp(rfpId) {
  const { data } = await client.post(`/rfp/${rfpId}/close`)
  return data
}

export async function deleteRfp(rfpId) {
  const { data } = await client.delete(`/rfp/${rfpId}`)
  return data
}

export async function getEvaluation(rfpId) {
  const { data } = await client.get(`/rfp/${rfpId}/evaluation`)
  return data
}

export async function resolvePendingEvidence(rfpId, bidId, criterionId, verdict, reasoning) {
  const { data } = await client.post(
    `/rfp/${rfpId}/bids/${bidId}/evidence/${criterionId}/resolve`,
    { verdict, reasoning },
  )
  return data
}

export async function getBidDocuments(rfpId, bidId) {
  const { data } = await client.get(`/rfp/${rfpId}/bids/${bidId}/documents`)
  return data
}

// A plain <a href> or window.open() can't attach an Authorization header,
// and this endpoint is JWT-gated like everything else under /rfp -- so the
// file is fetched through the same authenticated axios client as a blob,
// then handed to the browser as a throwaway object URL. Keeps the token in
// the header only, never in a URL (which would otherwise end up in browser
// history / server access logs).
export async function downloadBidDocument(rfpId, bidId, filename) {
  const { data } = await client.get(
    `/rfp/${rfpId}/bids/${bidId}/documents/${encodeURIComponent(filename)}`,
    { responseType: 'blob' },
  )
  const url = URL.createObjectURL(data)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export async function openFinancialBids(rfpId) {
  const { data } = await client.post(`/rfp/${rfpId}/open-financial-bids`)
  return data
}

export async function runL1Selection(rfpId, msePreferenceActive) {
  const { data } = await client.post(`/rfp/${rfpId}/run-l1-selection`, { mse_preference_active: msePreferenceActive })
  return data
}

export async function getNorms() {
  const { data } = await client.get('/admin/norms')
  return data.norms
}

export async function updateNormStatus(normName, status) {
  const { data } = await client.post(`/admin/norms/${encodeURIComponent(normName)}/status`, { status })
  return data
}

export async function uploadNorm(file, normName, version, effectiveDate) {
  const form = new FormData()
  form.append('file', file)
  form.append('norm_name', normName)
  if (version) form.append('version', version)
  if (effectiveDate) form.append('effective_date', effectiveDate)
  // Real ingestion of a full document (chunking + embedding every chunk)
  // takes 1-2 minutes -- axios has no default timeout, so this deliberately
  // waits for the real result rather than erroring out early.
  const { data } = await client.post('/admin/norms/upload', form)
  return data
}

export async function getUsers() {
  const { data } = await client.get('/admin/users')
  return data.users
}

export async function setUserActive(userId, isActive) {
  const { data } = await client.post(`/admin/users/${userId}/active`, { is_active: isActive })
  return data
}

export async function createBuyer(email, password, orgName) {
  const { data } = await client.post('/admin/users/buyer', { email, password, org_name: orgName })
  return data
}

export async function getFlaggedRfps() {
  const { data } = await client.get('/admin/flagged-rfps')
  return data.rfps
}

export { TOKEN_KEY }
export default client
