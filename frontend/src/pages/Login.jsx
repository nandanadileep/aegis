import { useEffect, useState } from 'react'
import { getSupabase } from '../lib/supabase'
import ThemeToggle from '../components/ThemeToggle'

export default function Login() {
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let cancel = false
    async function check() {
      const sb = await getSupabase()
      const { data: { session } } = await sb.auth.getSession()
      if (session && !cancel) await redirect(sb, session)
      sb.auth.onAuthStateChange(async (_e, s) => {
        if (s && !cancel) await redirect(sb, s)
      })
    }
    check()
    return () => { cancel = true }
  }, [])

  async function redirect(sb, session) {
    const res = await fetch('/api/me', { headers: { Authorization: `Bearer ${session.access_token}` } })
    const d = await res.json()
    window.location.href = d.exists ? '/chat' : '/onboarding'
  }

  async function signIn() {
    setLoading(true)
    setStatus('Redirecting…')
    const sb = await getSupabase()
    await sb.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: window.location.origin + '/login' },
    })
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', flexDirection: 'column', position: 'relative', overflow: 'hidden' }}>
      {/* Gradient blobs */}
      <div style={{
        position: 'absolute', inset: 0, zIndex: 0, pointerEvents: 'none',
        background: 'radial-gradient(ellipse 70% 60% at 20% 50%, rgba(255,107,53,0.35) 0%, transparent 70%), radial-gradient(ellipse 50% 70% at 80% 30%, rgba(34,211,238,0.3) 0%, transparent 65%), radial-gradient(ellipse 40% 50% at 50% 80%, rgba(225,29,72,0.25) 0%, transparent 60%)',
      }} />
      <div style={{
        position: 'absolute', inset: 0, zIndex: 0, pointerEvents: 'none',
        backgroundImage: 'url("data:image/svg+xml,%3Csvg viewBox=\'0 0 200 200\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cfilter id=\'n\'%3E%3CfeTurbulence type=\'fractalNoise\' baseFrequency=\'0.75\' numOctaves=\'4\' stitchTiles=\'stitch\'/%3E%3C/filter%3E%3Crect width=\'100%25\' height=\'100%25\' filter=\'url(%23n)\' opacity=\'0.04\'/%3E%3C/svg%3E")',
        backgroundRepeat: 'repeat', backgroundSize: '200px',
      }} />

      {/* Header */}
      <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 40px', height: 60, position: 'relative', zIndex: 10, borderBottom: '1px solid var(--border)' }}>
        <span style={{ fontSize: 15, fontWeight: 800, letterSpacing: '-0.03em', color: 'var(--text)' }}>Aegis</span>
        <ThemeToggle />
      </header>

      {/* Main */}
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '60px 20px', position: 'relative', zIndex: 10 }}>
        <div style={{ width: '100%', maxWidth: 420, animation: 'rise 0.5s cubic-bezier(0.22,1,0.36,1) both' }}>
          <style>{`@keyframes rise { from { opacity:0; transform:translateY(24px) } to { opacity:1; transform:translateY(0) } }`}</style>

          <p style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--text-2)', marginBottom: 16 }}>Welcome</p>
          <h1 style={{ fontSize: 'clamp(48px,8vw,80px)', fontWeight: 900, letterSpacing: '-0.04em', lineHeight: 1, color: 'var(--text)', marginBottom: 16 }}>Sign in.</h1>
          <p style={{ fontSize: 15, color: 'var(--text-2)', lineHeight: 1.6, marginBottom: 48 }}>Your digital twin lives here.<br />Sign in to continue building it.</p>

          <button
            onClick={signIn}
            disabled={loading}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
              width: '100%', padding: '16px 24px',
              background: 'var(--text)', color: 'var(--bg)',
              border: 'none', borderRadius: 40, fontSize: 15, fontWeight: 700,
              fontFamily: 'Inter, sans-serif', cursor: loading ? 'not-allowed' : 'pointer',
              transition: 'opacity 0.15s', opacity: loading ? 0.5 : 1,
              letterSpacing: '-0.01em',
            }}
          >
            <GoogleIcon />
            Continue with Google
          </button>

          {status && <p style={{ fontSize: 13, color: 'var(--text-2)', textAlign: 'center', marginTop: 16 }}>{status}</p>}

          <p style={{ fontSize: 12, color: 'var(--text-3)', textAlign: 'center', marginTop: 32, lineHeight: 1.6 }}>
            By signing in, you agree to keep your twin data private and secure.
          </p>
        </div>
      </div>
    </div>
  )
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18">
      <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z"/>
      <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"/>
      <path fill="#FBBC05" d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"/>
      <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 6.29C4.672 4.163 6.656 3.58 9 3.58z"/>
    </svg>
  )
}
