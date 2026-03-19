import { useState, useEffect } from 'react'

export default function ThemeToggle({ style }) {
  const [theme, setTheme] = useState(
    () => localStorage.getItem('identiti-theme') || 'dark'
  )

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('identiti-theme', theme)
  }, [theme])

  return (
    <button
      onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
      title="Toggle theme"
      style={{
        width: 32, height: 32, borderRadius: '50%',
        background: 'var(--surface)', border: '1px solid var(--border)',
        cursor: 'pointer', display: 'flex', alignItems: 'center',
        justifyContent: 'center', fontSize: 14, transition: 'all 0.15s',
        flexShrink: 0, ...style,
      }}
    >
      {theme === 'dark' ? '☀️' : '🌙'}
    </button>
  )
}
