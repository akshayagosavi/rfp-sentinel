import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const LOGIN_PATH = { buyer: '/login', bidder: '/bidder/login', admin: '/admin/login' }

export default function ProtectedRoute({ children, role }) {
  const { isAuthenticated, role: userRole } = useAuth()
  if (!isAuthenticated) {
    return <Navigate to={LOGIN_PATH[role] ?? '/login'} replace />
  }
  if (role && userRole !== role) {
    return <Navigate to="/" replace />
  }
  return children
}
