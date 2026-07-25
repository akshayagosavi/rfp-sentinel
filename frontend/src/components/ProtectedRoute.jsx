import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function ProtectedRoute({ children, role }) {
  const { isAuthenticated, role: userRole } = useAuth()
  if (!isAuthenticated) {
    return <Navigate to={role === 'bidder' ? '/bidder/login' : '/login'} replace />
  }
  if (role && userRole !== role) {
    return <Navigate to="/" replace />
  }
  return children
}
