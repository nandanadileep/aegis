import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { getSupabase, authHeaders } from '../lib/supabase'
import ThemeToggle from '../components/ThemeToggle'

export default function Chat() {
  const [session, setSession] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const transcript = useRef([])
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    let cancel = false
    getSupabase().then(sb => {
      sb.auth.getSession().then(({ data: { session: s } }) => {
        if (!s) { window.location.href = '/login'; return }
        if (!cancel) setSession(s)
        sb.auth.onAuthStateChange((_e, ns) => { if (!ns) window.location.href = '/login'; else setSession(ns) })
      })
    })
    return () => { cancel = true }
  }, [])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  async function signOut() {
    const sb = await getSupabase()
    try { await sb.auth.signOut() } catch {}
    window.location.href = '/login'
  }

  async function sendMessage() {
    const text = input.trim()
    if (!text || sending || !session) return
    setSending(true)
    setInput('')
    const userMsg = { role: 'user', text }
    setMessages(m => [...m, userMsg, { role: 'thinking' }])
    transcript.current.push(`You: ${text}`)

    try {
      const res = await fetch('/chat', { method: 'POST', headers: authHeaders(session), body: JSON.stringify({ message: text }) })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Server error')
      setMessages(m => [...m.filter(x => x.role !== 'thinking'), {
        role: 'assistant',
        text: data.reply || 'No response',
        addedNodes: data.added_nodes || [],
      }])
      transcript.current.push(`Assistant: ${data.reply}`)
    } catch (e) {
      setMessages(m => [...m.filter(x => x.role !== 'thinking'), { role: 'assistant', text: `Error: ${e.message}` }])
    } finally {
      setSending(false)
      inputRef.current?.focus()
    }
  }

  async function saveTranscript() {
    if (!transcript.current.length || !session) return
    try {
      await fetch('/save', { method: 'POST', headers: authHeaders(session), body: JSON.stringify({ transcript: transcript.current.join('\n') }) })
      transcript.current = []
    } catch {}
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--bg)', overflow: 'hidden', position: 'relative' }}>
      {/* Subtle gradient background */}
      <div style={{ position: 'absolute', inset: 0, zIndex: 0, pointerEvents: 'none',
        background: 'radial-gradient(ellipse 60% 50% at 0% 100%, rgba(255,107,53,0.07) 0%, transparent 60%), radial-gradient(ellipse 50% 40% at 100% 0%, rgba(34,211,238,0.07) 0%, transparent 60%)',
      }} />

      {/* Header */}
      <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 32px', height: 60, borderBottom: '1px solid var(--border)', flexShrink: 0, background: 'var(--bg)', zIndex: 10, position: 'relative' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ fontSize: 15, fontWeight: 800, letterSpacing: '-0.03em', color: 'var(--text)' }}>Identiti</span>
          <nav style={{ display: 'flex', gap: 4 }}>
            <NavLink to="/chat" active>Chat</NavLink>
            <NavLink to="/memory">Graph</NavLink>
          </nav>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <ThemeToggle />
          <BtnSm onClick={saveTranscript}>Save</BtnSm>
          <BtnPrimary onClick={signOut}>Sign out</BtnPrimary>
        </div>
      </header>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '48px 0 24px', display: 'flex', flexDirection: 'column', gap: 2, position: 'relative', zIndex: 10 }}>
        {messages.length === 0 && <EmptyState />}
        {messages.map((m, i) => <Message key={i} msg={m} />)}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ flexShrink: 0, padding: '12px 24px 32px', maxWidth: 680, margin: '0 auto', width: '100%', position: 'relative', zIndex: 10 }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: 'var(--input-bg)', border: '1px solid var(--border)',
          borderRadius: 26, padding: '8px 8px 8px 20px',
          transition: 'border-color 0.2s, box-shadow 0.2s',
        }}
          onFocus={e => { e.currentTarget.style.borderColor = 'var(--border-strong)'; e.currentTarget.style.boxShadow = '0 0 0 3px var(--focus-shadow)' }}
          onBlur={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.boxShadow = 'none' }}
        >
          <input
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') sendMessage() }}
            placeholder="Message your twin…"
            autoComplete="off"
            style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: 'var(--text)', fontFamily: 'Inter, sans-serif', fontSize: 14, padding: '4px 0', minWidth: 0 }}
          />
          <button
            onClick={sendMessage}
            disabled={sending || !input.trim()}
            style={{
              width: 34, height: 34, borderRadius: '50%', background: sending ? 'var(--border)' : 'var(--send-bg)',
              border: 'none', cursor: sending ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center',
              justifyContent: 'center', flexShrink: 0, fontSize: 15, color: 'var(--send-text)', fontWeight: 700,
              transition: 'opacity 0.15s, transform 0.15s',
            }}
          >↑</button>
        </div>
      </div>
    </div>
  )
}

function EmptyState() {
  const h = new Date().getHours()
  const { greeting, sub } =
    h >= 5  && h < 9  ? { greeting: 'Good morning.', sub: 'Early start. Your memory is ready when you are.' } :
    h >= 9  && h < 12 ? { greeting: 'Good morning.', sub: 'Everything you\'ve built lives here. Start talking.' } :
    h >= 12 && h < 17 ? { greeting: 'Good afternoon.', sub: 'Your context is with you. Pick up where you left off.' } :
    h >= 17 && h < 21 ? { greeting: 'Good evening.', sub: 'Wind down or level up — your memory\'s here either way.' } :
                        { greeting: 'Hey, night owl.', sub: 'Late night thinking hits different. Let\'s capture it.' }
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8, paddingBottom: 80, pointerEvents: 'none' }}>
      <p style={{ fontSize: 18, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text)' }}>{greeting}</p>
      <p style={{ fontSize: 14, color: 'var(--text-3)', textAlign: 'center', maxWidth: 260, lineHeight: 1.6 }}>{sub}</p>
    </div>
  )
}

function Message({ msg }) {
  if (msg.role === 'thinking') {
    return (
      <div style={{ display: 'flex', width: '100%', maxWidth: 680, margin: '0 auto', padding: '3px 24px', justifyContent: 'flex-start' }}>
        <div style={{ background: 'transparent', color: 'var(--text-3)', fontSize: 13, padding: '4px 0' }}>
          <ThinkingDots />
        </div>
      </div>
    )
  }
  const isUser = msg.role === 'user'
  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', maxWidth: 680, margin: '0 auto', padding: '3px 24px', alignItems: isUser ? 'flex-end' : 'flex-start' }}>
      <div style={{
        maxWidth: '72%', padding: '11px 16px', fontSize: 14, lineHeight: 1.6,
        whiteSpace: 'pre-wrap', overflowWrap: 'anywhere',
        background: isUser ? 'var(--user-bubble)' : 'var(--asst-bubble)',
        color: isUser ? 'var(--user-bubble-text)' : 'var(--asst-bubble-text)',
        borderRadius: isUser ? '20px 20px 4px 20px' : '20px 20px 20px 4px',
        backdropFilter: isUser ? 'none' : 'blur(8px)',
        border: isUser ? 'none' : '1px solid var(--asst-bubble-border, transparent)',
        boxShadow: isUser ? 'none' : '0 1px 3px rgba(0,0,0,0.04)',
      }}
        dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.text) }}
      />
      {msg.addedNodes?.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 6, maxWidth: '72%' }}>
          {msg.addedNodes.map((n, i) => (
            <span key={i} style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              padding: '3px 9px', borderRadius: 20, fontSize: 11, fontWeight: 600,
              background: 'rgba(0,0,238,0.08)', border: '1px solid rgba(0,0,238,0.2)', color: '#0000ee',
              letterSpacing: '-0.01em',
            }}>
              <span style={{ opacity: 0.6 }}>✦</span> {n.name} · {n.label}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function ThinkingDots() {
  return (
    <>
      <style>{`
        @keyframes blink { 0%,80%,100%{opacity:.3} 40%{opacity:1} }
        .td span { opacity:.3; animation: blink 1.4s infinite; display:inline-block; }
        .td span:nth-child(2){animation-delay:.2s}
        .td span:nth-child(3){animation-delay:.4s}
      `}</style>
      <span className="td"><span>●</span><span>●</span><span>●</span></span>
    </>
  )
}

function renderMarkdown(text) {
  return text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\*\*([^*\n][\s\S]*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`\n]+)`/g, '<code style="font-family:monospace;font-size:0.88em;background:rgba(255,255,255,0.1);padding:1px 5px;border-radius:4px">$1</code>')
}

function NavLink({ to, children, active }) {
  return (
    <a href={to} style={{
      padding: '6px 14px', borderRadius: 80, fontSize: 13, fontWeight: 500,
      color: active ? 'var(--text)' : 'var(--text-2)', textDecoration: 'none',
      border: active ? '1px solid var(--border-strong)' : '1px solid transparent',
      background: active ? 'var(--surface)' : 'transparent', transition: 'all 0.15s',
    }}>{children}</a>
  )
}

function BtnSm({ onClick, children }) {
  return (
    <button onClick={onClick} style={{
      padding: '7px 16px', borderRadius: 40, fontSize: 13, fontWeight: 600,
      cursor: 'pointer', fontFamily: 'Inter, sans-serif', background: 'var(--bg)',
      color: 'var(--text)', border: '1px solid var(--border-strong)', transition: 'all 0.15s',
    }}>{children}</button>
  )
}

function BtnPrimary({ onClick, children }) {
  return (
    <button onClick={onClick} style={{
      padding: '7px 16px', borderRadius: 40, fontSize: 13, fontWeight: 600,
      cursor: 'pointer', fontFamily: 'Inter, sans-serif', background: 'var(--text)',
      color: 'var(--bg)', border: 'none', transition: 'all 0.15s',
    }}>{children}</button>
  )
}
