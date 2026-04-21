import { useState, useRef, FormEvent } from 'react'
import { useNavigate, Navigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../contexts/AuthContext'
import api from '../api/client'

export default function LoginPage() {
  const { t } = useTranslation()
  const { login, isAuthenticated } = useAuth()
  const navigate = useNavigate()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [mfaRequired, setMfaRequired] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const codeRef = useRef<HTMLInputElement>(null)

  if (isAuthenticated) return <Navigate to="/dashboard" replace />

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const body: Record<string, string> = { username, password }
      if (mfaRequired) body.code = code
      const res = await api.post('/auth/login', body)
      login(res.data.token)
      navigate('/dashboard', { replace: true })
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number; data?: { detail?: string } } })
        ?.response?.status
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      if (status === 400 && detail === 'mfa_required') {
        if (!mfaRequired) {
          setMfaRequired(true)
          setTimeout(() => codeRef.current?.focus(), 50)
        } else {
          setError(t('login.invalidCode'))
        }
      } else if (status === 503) {
        setError(t('login.paperlessNotConfigured'))
      } else {
        setError(t('login.invalidCredentials'))
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="bg-white rounded-xl shadow-md w-full max-w-sm p-8">
        <div className="flex flex-col items-center mb-6">
          <img src="/icon.png" alt="Paperless-AIssist" className="w-16 h-16 rounded mb-3" />
          <h1 className="text-xl font-bold text-gray-900">Paperless-AIssist</h1>
          <p className="text-sm text-gray-500 mt-1">{t('login.hint')}</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('login.username')}
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus={!mfaRequired}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {t('login.password')}
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          {mfaRequired && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('login.mfaCode')}
              </label>
              <input
                ref={codeRef}
                type="text"
                inputMode="numeric"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 tracking-widest text-center text-lg"
              />
              <p className="text-xs text-gray-500 mt-1">{t('login.mfaHint')}</p>
            </div>
          )}
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 px-4 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
          >
            {loading
              ? mfaRequired
                ? t('login.verifying')
                : t('login.signingIn')
              : mfaRequired
                ? t('login.verify')
                : t('login.signIn')}
          </button>
        </form>
      </div>
    </div>
  )
}
