import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import { ThemeProvider } from './context/ThemeContext'
import ProtectedRoute from './components/ProtectedRoute'
import Landing from './pages/Landing'
import About from './pages/About'
import Bids from './pages/Bids'
import BidDetail from './pages/BidDetail'
import BuyerLogin from './pages/BuyerLogin'
import BuyerDashboard from './pages/BuyerDashboard'
import BuyerRfps from './pages/BuyerRfps'
import RfpManage from './pages/RfpManage'
import BidderLogin from './pages/BidderLogin'
import BidderSignup from './pages/BidderSignup'
import BidderDashboard from './pages/BidderDashboard'
import BidSubmission from './pages/BidSubmission'
import Profile from './pages/Profile'
import AdminLogin from './pages/AdminLogin'
import AdminDashboard from './pages/AdminDashboard'

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/about" element={<About />} />

            {/* Public -- no login needed to browse, matching real GeM */}
            <Route path="/bids" element={<Bids />} />
            <Route path="/bids/:rfpId" element={<BidDetail />} />

            <Route path="/login" element={<BuyerLogin />} />
            <Route
              path="/buyer/dashboard"
              element={
                <ProtectedRoute role="buyer">
                  <BuyerDashboard />
                </ProtectedRoute>
              }
            />
            <Route
              path="/buyer/rfps"
              element={
                <ProtectedRoute role="buyer">
                  <BuyerRfps />
                </ProtectedRoute>
              }
            />
            <Route
              path="/buyer/rfp/:rfpId"
              element={
                <ProtectedRoute role="buyer">
                  <RfpManage />
                </ProtectedRoute>
              }
            />

            <Route path="/bidder/login" element={<BidderLogin />} />
            <Route path="/bidder/signup" element={<BidderSignup />} />
            <Route
              path="/bidder/dashboard"
              element={
                <ProtectedRoute role="bidder">
                  <BidderDashboard />
                </ProtectedRoute>
              }
            />
            <Route
              path="/bidder/submit/:rfpId"
              element={
                <ProtectedRoute role="bidder">
                  <BidSubmission />
                </ProtectedRoute>
              }
            />

            <Route
              path="/profile"
              element={
                <ProtectedRoute>
                  <Profile />
                </ProtectedRoute>
              }
            />

            <Route path="/admin/login" element={<AdminLogin />} />
            <Route
              path="/admin/dashboard"
              element={
                <ProtectedRoute role="admin">
                  <AdminDashboard />
                </ProtectedRoute>
              }
            />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  )
}
