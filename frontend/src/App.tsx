import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { api } from './api/client'
import type { User } from './api/types'
import ChatPage from './pages/ChatPage'
import LoginPage from './pages/LoginPage'

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center text-navy">
        <div className="flex items-center gap-3 text-sm tracking-wide">
          <span className="typing-dots">
            <span />
            <span />
            <span />
          </span>
          Loading DocChat…
        </div>
      </div>
    )
  }

  return (
    <Routes>
      <Route
        path="/login"
        element={user ? <Navigate to="/" replace /> : <LoginPage onLogin={setUser} />}
      />
      <Route
        path="/*"
        element={
          user ? (
            <ChatPage user={user} onLogout={() => setUser(null)} />
          ) : (
            <Navigate to="/login" replace />
          )
        }
      />
    </Routes>
  )
}
