import { useEffect, useRef, useState } from 'react'
import { getSupabase, authHeaders } from '../lib/supabase'
import ThemeToggle from '../components/ThemeToggle'

export default function Onboarding() {
  const [screen, setScreen] = useState('welcome') // welcome | chat | import1 | import2 | success
  const [session, setSession] = useState(null)
  const [autoUsername, setAutoUsername] = useState('')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [importJson, setImportJson] = useState('')
  const [importErr, setImportErr] = useState('')
  const [importing, setImporting] = useState(false)
  const chatHistory = useRef([])
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    getSupabase().then(sb => {
      sb.auth.getSession().then(async ({ data: { session: s } }) => {
        if (!s) { window.location.href = '/login'; return }
        setSession(s)
        const res = await fetch('/api/me', { headers: { Authorization: `Bearer ${s.access_token}` } })
        const d = await res.json()
        if (d.exists) { window.location.href = '/chat'; return }
        setAutoUsername(genUsername(s))
        sb.auth.onAuthStateChange((_e, ns) => { if (!ns) window.location.href = '/login'; else setSession(ns) })
      })
    })
  }, [])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  function genUsername(s) {
    const meta = s.user?.user_metadata || {}
    const full = meta.full_name || meta.name || meta.email || 'user'
    const first = full.split(' ')[0].toLowerCase().replace(/[^a-z0-9]/g, '')
    return `${first}${Math.floor(Math.random() * 900 + 100)}`
  }

  function startChat() {
    chatHistory.current = []
    setMessages([])
    setScreen('chat')
    sendOnboard('')
  }

  async function sendOnboard(userText) {
    if (sending || !session) return
    setSending(true)
    if (userText) {
      const msg = { role: 'user', text: userText }
      setMessages(m => [...m, msg])
      chatHistory.current.push({ role: 'user', content: userText })
    }
    setInput('')
    setMessages(m => [...m, { role: 'thinking' }])

    try {
      const res = await fetch('/api/onboard-chat', {
        method: 'POST', headers: authHeaders(session),
        body: JSON.stringify({ message: userText, history: chatHistory.current }),
      })
      const data = await res.json()
      setMessages(m => {
        const filtered = m.filter(x => x.role !== 'thinking')
        return data.reply ? [...filtered, { role: 'assistant', text: data.reply }] : filtered
      })
      if (data.reply) chatHistory.current.push({ role: 'assistant', content: data.reply })
      if (data.profile) await saveProfile(data.profile)
    } catch {
      setMessages(m => [...m.filter(x => x.role !== 'thinking'), { role: 'assistant', text: 'Something went wrong. Try again.' }])
    } finally {
      setSending(false)
      inputRef.current?.focus()
    }
  }

  async function saveProfile(profile) {
    try {
      const resp = await fetch('/api/import', {
        method: 'POST', headers: authHeaders(session),
        body: JSON.stringify({ twin: profile, username: autoUsername }),
      })
      if (!resp.ok) throw new Error()
      setTimeout(() => setScreen('success'), 1800)
    } catch {
      setMessages(m => [...m, { role: 'assistant', text: "I have everything I need — but hit an issue saving. Try again?" }])
    }
  }

  async function importTwin() {
    setImportErr('')
    const raw = importJson.trim()
    if (!raw) { setImportErr('Paste your memory export first.'); return }
    setImporting(true)
    try {
      const resp = await fetch('/api/import', {
        method: 'POST', headers: authHeaders(session),
        body: JSON.stringify({ raw_memory: raw, username: autoUsername }),
      })
      if (!resp.ok) throw new Error()
      setScreen('success')
    } catch { setImportErr('Import failed. Please try again.') }
    finally { setImporting(false) }
  }

  async function downloadCard() {
    const resp = await fetch('/api/wallet', { headers: authHeaders(session) })
    const blob = await resp.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob); a.download = 'memory_card.md'; a.click()
    URL.revokeObjectURL(a.href)
  }

  if (screen === 'welcome') return <WelcomeScreen onBuild={startChat} onImport={() => setScreen('import1')} />
  if (screen === 'chat') return <ChatScreen messages={messages} input={input} setInput={setInput} onSend={() => input.trim() && sendOnboard(input.trim())} sending={sending} inputRef={inputRef} bottomRef={bottomRef} onBack={() => setScreen('welcome')} />
  if (screen === 'import1') return <Import1Screen onBack={() => setScreen('welcome')} onNext={() => setScreen('import2')} />
  if (screen === 'import2') return <Import2Screen value={importJson} onChange={setImportJson} onBack={() => setScreen('import1')} onImport={importTwin} importing={importing} error={importErr} />
  if (screen === 'success') return <SuccessScreen onGraph={() => window.location.href = '/memory'} onCard={downloadCard} />
  return null
}

function WelcomeScreen({ onBuild, onImport }) {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', flexDirection: 'column', position: 'relative', overflow: 'hidden' }}>
      <Blobs />
      <div style={{ position: 'absolute', top: 20, right: 24, zIndex: 20 }}><ThemeToggle /></div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 20px', position: 'relative', zIndex: 10 }}>
        <style>{`@keyframes rise{from{opacity:0;transform:translateY(24px)}to{opacity:1;transform:translateY(0)}}`}</style>
        <div style={{ animation: 'rise 0.5s cubic-bezier(0.22,1,0.36,1) both', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0 }}>
          <h1 style={{ fontSize: 'clamp(48px,10vw,88px)', fontWeight: 900, letterSpacing: '-0.04em', lineHeight: 1, textAlign: 'left', color: 'var(--text)', marginBottom: 10, width: '100%' }}>Identiti.</h1>
          <p style={{ fontSize: 16, color: 'var(--text-2)', textAlign: 'left', lineHeight: 1.6, marginBottom: 20, width: '100%' }}>Your context is with you.</p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, width: '100%', maxWidth: 580 }}>
            <Card icon="↗" title="Import from AI." desc="Bring that over." onClick={onImport} />
            <Card icon="✦" title="Chat with our AI." desc="Your profile builds itself as you talk." onClick={onBuild} primary />
          </div>
        </div>
      </div>
    </div>
  )
}

function Card({ icon, title, desc, onClick, primary }) {
  const [hover, setHover] = useState(false)
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        background: hover ? 'var(--surface-hover)' : 'var(--surface)',
        border: `1px solid ${hover ? 'var(--border-strong)' : 'var(--border)'}`,
        borderRadius: 16, padding: '28px 24px', cursor: 'pointer',
        transition: 'all 0.18s', textAlign: 'left', userSelect: 'none',
        transform: hover ? 'translateY(-3px)' : 'none',
      }}
    >
      <div style={{ fontSize: 22, marginBottom: 14 }}>{icon}</div>
      <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6, letterSpacing: '-0.01em', color: 'var(--text)' }}>{title}</div>
      <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.5 }}>{desc}</div>
    </div>
  )
}

function ChatScreen({ messages, input, setInput, onSend, sending, inputRef, bottomRef, onBack }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--bg)', overflow: 'hidden', position: 'relative' }}>
      <Blobs opacity={0.04} />
      <div style={{ position: 'absolute', top: 20, right: 24, zIndex: 20 }}><ThemeToggle /></div>
      <header style={{ display: 'flex', alignItems: 'center', padding: '0 32px', height: 60, borderBottom: '1px solid var(--border)', flexShrink: 0, background: 'var(--bg)', zIndex: 10, gap: 12, position: 'relative' }}>
        <button onClick={onBack} style={{ background: 'none', border: 'none', color: 'var(--text-2)', fontSize: 15, cursor: 'pointer', fontFamily: 'Inter, sans-serif' }}>←</button>
        <span style={{ fontSize: 15, fontWeight: 700, letterSpacing: '-0.01em', color: 'var(--text)' }}>Chat</span>
      </header>
      <div style={{ flex: 1, overflowY: 'auto', padding: '40px 0 16px', display: 'flex', flexDirection: 'column', gap: 2, position: 'relative', zIndex: 10 }}>
        {messages.map((m, i) => <MsgBubble key={i} msg={m} />)}
        <div ref={bottomRef} />
      </div>
      <div style={{ flexShrink: 0, padding: '12px 24px 32px', maxWidth: 680, margin: '0 auto', width: '100%', position: 'relative', zIndex: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--input-bg)', border: '1px solid var(--border)', borderRadius: 26, padding: '8px 8px 8px 20px' }}>
          <input ref={inputRef} value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') onSend() }}
            placeholder="Type a message…" autoComplete="off"
            style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: 'var(--text)', fontFamily: 'Inter, sans-serif', fontSize: 14, padding: '4px 0', minWidth: 0 }} />
          <button onClick={onSend} disabled={sending || !input.trim()}
            style={{ width: 34, height: 34, borderRadius: '50%', background: sending ? 'var(--border)' : 'var(--send-bg)', border: 'none', cursor: sending ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15, color: 'var(--send-text)', fontWeight: 700 }}>↑</button>
        </div>
      </div>
    </div>
  )
}

function MsgBubble({ msg }) {
  if (msg.role === 'thinking') return (
    <div style={{ display: 'flex', width: '100%', maxWidth: 680, margin: '0 auto', padding: '3px 24px' }}>
      <div style={{ color: 'var(--text-3)', fontSize: 13 }}>
        <style>{`@keyframes blink{0%,80%,100%{opacity:.3}40%{opacity:1}}.td2 span{opacity:.3;animation:blink 1.4s infinite;display:inline-block}.td2 span:nth-child(2){animation-delay:.2s}.td2 span:nth-child(3){animation-delay:.4s}`}</style>
        <span className="td2"><span>●</span><span>●</span><span>●</span></span>
      </div>
    </div>
  )
  const isUser = msg.role === 'user'
  return (
    <div style={{ display: 'flex', width: '100%', maxWidth: 680, margin: '0 auto', padding: '3px 24px', justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
      <div style={{ maxWidth: '72%', padding: '11px 16px', fontSize: 14, lineHeight: 1.6, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', background: isUser ? 'var(--user-bubble)' : 'var(--asst-bubble)', color: isUser ? 'var(--user-bubble-text)' : 'var(--asst-bubble-text)', borderRadius: isUser ? '20px 20px 4px 20px' : '20px 20px 20px 4px' }}>{msg.text}</div>
    </div>
  )
}

function Import1Screen({ onBack, onNext }) {
  const [copied, setCopied] = useState(false)
  const prompt = `Look through everything you know about me — your stored memories, past conversations, preferences, context you've picked up over time. Then output a JSON profile based only on what you actually know. No guessing.\n\n\`\`\`json\n{\n  "name": "",\n  "description": "one sentence — who this person is",\n  "values": [],\n  "skills": [],\n  "personality": [],\n  "goals": [],\n  "speaking_style": "",\n  "known_for": []\n}\n\`\`\`\n\nOnly include fields where you have real information. Leave arrays empty if unsure. Output the JSON block only, no explanation.`
  function copy() { navigator.clipboard.writeText(prompt).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2200) }) }
  return (
    <ImportLayout onBack={onBack} step="Step 1 of 2" title="Export your memory" sub="Copy this into ChatGPT or Claude — any AI that knows you. Paste back the JSON it gives you.">
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, padding: 20, fontFamily: 'monospace', fontSize: 12.5, color: 'var(--text-2)', lineHeight: 1.65, whiteSpace: 'pre-wrap', width: '100%', marginBottom: 16, wordBreak: 'break-word' }}>{prompt}</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
        <Btn onClick={copy}>{copied ? 'Copied ✓' : 'Copy prompt'}</Btn>
        <BtnFill onClick={onNext}>I have it →</BtnFill>
      </div>
    </ImportLayout>
  )
}

function Import2Screen({ value, onChange, onBack, onImport, importing, error }) {
  return (
    <ImportLayout onBack={onBack} step="Step 2 of 2" title="Paste what it gave you" sub="Drop the memory export below. We'll parse it automatically.">
      <textarea value={value} onChange={e => onChange(e.target.value)} rows={10}
        placeholder='Paste your memory export here…'
        style={{ width: '100%', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, color: 'var(--text)', fontFamily: 'monospace', fontSize: 12.5, padding: '14px 16px', outline: 'none', resize: 'none', lineHeight: 1.5, marginBottom: 16 }} />
      <BtnFill onClick={onImport} disabled={importing}>{importing ? 'Importing…' : 'Import'}</BtnFill>
      {error && <p style={{ color: '#ff3b30', fontSize: 13, textAlign: 'center', marginTop: 12 }}>{error}</p>}
    </ImportLayout>
  )
}

function ImportLayout({ onBack, step, title, sub, children }) {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '32px 20px', position: 'relative' }}>
      <Blobs opacity={0.04} />
      <div style={{ position: 'absolute', top: 20, right: 24, zIndex: 20 }}><ThemeToggle /></div>
      <div style={{ width: '100%', maxWidth: 600, display: 'flex', flexDirection: 'column', alignItems: 'center', position: 'relative', zIndex: 10 }}>
        <button onClick={onBack} style={{ background: 'none', border: 'none', color: 'var(--text-2)', fontSize: 14, cursor: 'pointer', fontFamily: 'Inter, sans-serif', alignSelf: 'flex-start', marginBottom: 32 }}>← Back</button>
        <p style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--text-3)', marginBottom: 14 }}>{step}</p>
        <h2 style={{ fontSize: 'clamp(24px,4vw,36px)', fontWeight: 800, letterSpacing: '-0.03em', color: 'var(--text)', marginBottom: 12, textAlign: 'center' }}>{title}</h2>
        <p style={{ fontSize: 14, color: 'var(--text-2)', textAlign: 'center', lineHeight: 1.6, marginBottom: 32, maxWidth: 440 }}>{sub}</p>
        {children}
      </div>
    </div>
  )
}

function SuccessScreen({ onGraph, onCard }) {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '32px 20px', position: 'relative' }}>
      <Blobs />
      <div style={{ position: 'relative', zIndex: 10, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 0 }}>
        <div style={{ width: 72, height: 72, borderRadius: '50%', background: 'var(--surface)', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 30, marginBottom: 24 }}>✓</div>
        <h2 style={{ fontSize: 'clamp(28px,5vw,48px)', fontWeight: 900, letterSpacing: '-0.04em', color: 'var(--text)', marginBottom: 12, textAlign: 'center' }}>Your profile is built.</h2>
        <p style={{ fontSize: 15, color: 'var(--text-2)', textAlign: 'center', lineHeight: 1.6, marginBottom: 40, maxWidth: 400 }}>Your profile is live in the graph. Download your Memory Card and paste it into any AI.</p>
        <div style={{ display: 'flex', gap: 12 }}>
          <Btn onClick={onGraph}>View graph</Btn>
          <BtnFill onClick={onCard}>Download Memory Card</BtnFill>
        </div>
      </div>
    </div>
  )
}

function Blobs({ opacity = 0.55 }) {
  return (
    <div style={{ position: 'absolute', inset: 0, zIndex: 0, pointerEvents: 'none',
      background: `radial-gradient(ellipse 70% 60% at 15% 50%, rgba(255,107,53,${opacity}) 0%, transparent 70%), radial-gradient(ellipse 50% 70% at 85% 25%, rgba(34,211,238,${opacity * 0.85}) 0%, transparent 65%), radial-gradient(ellipse 40% 50% at 50% 85%, rgba(225,29,72,${opacity * 0.7}) 0%, transparent 60%)`,
    }} />
  )
}

function Btn({ onClick, children, disabled }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{ padding: '10px 22px', borderRadius: 40, fontSize: 14, fontWeight: 600, cursor: disabled ? 'not-allowed' : 'pointer', border: '1px solid var(--border-strong)', background: 'var(--bg)', color: 'var(--text)', fontFamily: 'Inter, sans-serif', transition: 'all 0.15s', opacity: disabled ? 0.5 : 1 }}>{children}</button>
  )
}

function BtnFill({ onClick, children, disabled }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{ padding: '10px 22px', borderRadius: 40, fontSize: 14, fontWeight: 700, cursor: disabled ? 'not-allowed' : 'pointer', border: 'none', background: 'var(--text)', color: 'var(--bg)', fontFamily: 'Inter, sans-serif', transition: 'all 0.15s', opacity: disabled ? 0.5 : 1 }}>{children}</button>
  )
}
