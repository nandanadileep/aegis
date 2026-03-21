import { useEffect, useState } from 'react'
import { getSupabase } from '../lib/supabase'
import { API } from '../lib/api'
import ThemeToggle from '../components/ThemeToggle'
import styles from './Login.module.css'

export default function Login() {
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let cancel = false
    async function check() {
      let sb
      try { sb = await getSupabase() } catch (e) { setStatus(e.message); return }
      const { data: { session } } = await sb.auth.getSession()
      if (session && !cancel) await redirect(sb, session)
      sb.auth.onAuthStateChange(async (event, s) => {
        if ((event === 'SIGNED_IN' || event === 'INITIAL_SESSION') && s && !cancel) await redirect(sb, s)
      })
    }
    check()
    return () => { cancel = true }
  }, [])

  async function redirect(sb, session) {
    try {
      await fetch(`${API}/api/me`, { headers: { Authorization: `Bearer ${session.access_token}` } })
    } catch {}
    window.location.href = '/onboarding'
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
    <div className={styles.root}>
      <div className={styles.blobGradient} />
      <div className={styles.blobNoise} />

      <header className={styles.header}>
        <span className={styles.brand}>Identiti</span>
        <ThemeToggle />
      </header>

      <div className={styles.main}>
        <div className={styles.card}>
          <p className={styles.label}>Welcome</p>
          <h1 className={styles.heading}>Identiti.</h1>
          <p className={styles.subtitle}>Your memory is with you.<br />Sign in to continue.</p>

          <button
            onClick={signIn}
            disabled={loading}
            className={styles.signInBtn}
          >
            <GoogleIcon />
            Continue with Google
          </button>

          {status && <p className={styles.statusText}>{status}</p>}
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
