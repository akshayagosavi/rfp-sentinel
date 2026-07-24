import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import { ThemeProvider } from './context/ThemeContext'
import ProtectedRoute from './components/ProtectedRoute'
import Landing from './pages/Landing'
import BuyerLogin from './pages/BuyerLogin'
import BuyerDashboard from './pages/BuyerDashboard'
import BidderLogin from './pages/BidderLogin'
import BidderDashboard from './pages/BidderDashboard'
import BidderRfpDetail from './pages/BidderRfpDetail'
import ComingSoon from './pages/ComingSoon'

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<BuyerLogin />} />
            <Route
              path="/buyer/dashboard"
              element={
                <ProtectedRoute role="buyer">
                  <BuyerDashboard />
                </ProtectedRoute>
              }
            />
            <Route path="/bidder/login" element={<BidderLogin />} />
            <Route
              path="/bidder/dashboard"
              element={
                <ProtectedRoute role="bidder">
                  <BidderDashboard />
                </ProtectedRoute>
              }
            />
            <Route
              path="/bidder/rfp/:rfpId"
              element={
                <ProtectedRoute role="bidder">
                  <BidderRfpDetail />
                </ProtectedRoute>
              }
            />
            <Route path="/admin/dashboard" element={<ComingSoon role="Admin" />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  )
}
