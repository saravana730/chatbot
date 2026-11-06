import { useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../api/client'
import type { User } from '../api/types'

export default function LoginPage({ onLogin }: { onLogin: (user: User) => void }) {
  const [email, setEmail] = useState('admin@docchat.com')
  const [password, setPassword] = useState('password')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const user = await api.login(email, password)
      onLogin(user)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_15%_10%,rgba(29,111,216,0.18),transparent_40%),radial-gradient(circle_at_90%_0%,rgba(11,58,110,0.14),transparent_42%)]" />
      <div className="relative mx-auto flex min-h-screen max-w-6xl flex-col justify-center px-6 py-16 lg:flex-row lg:items-center lg:gap-24">
        <div className="animate-rise mb-12 max-w-xl lg:mb-0">
          <p className="font-display text-5xl leading-none text-navy md:text-7xl">DocChat</p>
          <p className="mt-5 max-w-md text-lg text-muted">
            Your documents, one conversation. Upload English policies and manuals, then ask with
            clarity.
          </p>
          <p className="mt-3 text-sm text-muted">English-only · OCR and answers are English</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="animate-rise w-full max-w-md rounded-3xl border border-line bg-white/90 p-8 shadow-[0_24px_70px_rgba(11,58,110,0.1)] backdrop-blur"
          style={{ animationDelay: '80ms' }}
        >
          <h1 className="font-display text-2xl text-navy">Sign in</h1>
          <p className="mt-1 text-sm text-muted">Welcome back to DocChat</p>

          <label className="mt-6 block text-sm font-medium text-navy">
            Email
            <input
              className="mt-1.5 w-full rounded-xl border border-line bg-ice px-3 py-2.5 outline-none transition focus:border-blue focus:ring-2 focus:ring-blue/20"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="username"
            />
          </label>

          <label className="mt-4 block text-sm font-medium text-navy">
            Password
            <input
              className="mt-1.5 w-full rounded-xl border border-line bg-ice px-3 py-2.5 outline-none transition focus:border-blue focus:ring-2 focus:ring-blue/20"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
          </label>

          {error && <p className="mt-4 text-sm text-danger">{error}</p>}

          <button
            type="submit"
            disabled={busy}
            className="mt-6 w-full rounded-xl bg-blue px-4 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-navy disabled:opacity-60"
          >
            {busy ? 'Signing in…' : 'Enter DocChat'}
          </button>
        </form>
      </div>
    </div>
  )
}
