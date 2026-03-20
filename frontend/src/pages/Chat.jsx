import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { getSupabase, authHeaders } from '../lib/supabase'
import ThemeToggle from '../components/ThemeToggle'

const BYOK_PROVIDERS = [
  { label: 'Groq',      model: 'groq/llama-3.3-70b-versatile',  ph: 'gsk_...' },
  { label: 'OpenAI',    model: 'openai/gpt-4o',                  ph: 'sk-...' },
  { label: 'Anthropic', model: 'anthropic/claude-sonnet-4-6',    ph: 'sk-ant-...' },
  { label: 'Custom',    model: '',                                ph: 'API key' },
]

export default function Chat() {
  const [session, setSession] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [byokOpen, setByokOpen] = useState(false)
  const [byokProvider, setByokProvider] = useState(0)
  const [byokModel, setByokModel] = useState('')
  const [byokKey, setByokKey] = useState('')
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

  useEffect(() => {
    const k = localStorage.getItem('byok_key') || ''
    const m = localStorage.getItem('byok_model') || ''
    if (k) setByokKey(k)
    if (m) {
      setByokModel(m)
      const pi = BYOK_PROVIDERS.findIndex(p => p.model === m)
      setByokProvider(pi >= 0 ? pi : BYOK_PROVIDERS.length - 1)
    }
  }, [])

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
          <BtnSm onClick={() => setByokOpen(true)}>
            {localStorage.getItem('byok_key') ? 'Key set' : 'API Key'}
          </BtnSm>
          <BtnSm onClick={saveTranscript}>Save</BtnSm>
          <BtnPrimary onClick={signOut}>Sign out</BtnPrimary>
        </div>
      </header>

      {byokOpen && (
        <div style={{ position:'fixed', inset:0, zIndex:100, display:'flex', alignItems:'center', justifyContent:'center', background:'rgba(0,0,0,0.4)', backdropFilter:'blur(4px)' }}
          onClick={e => { if(e.target===e.currentTarget) setByokOpen(false) }}>
          <div style={{ background:'var(--bg)', border:'1px solid var(--border)', borderRadius:16, padding:28, width:360, boxShadow:'0 24px 64px rgba(0,0,0,0.18)' }}>
            <h3 style={{ fontSize:16, fontWeight:800, letterSpacing:'-0.02em', marginBottom:4, color:'var(--text)' }}>Your API Key</h3>
            <p style={{ fontSize:12, color:'var(--text-3)', marginBottom:20, lineHeight:1.6 }}>Your key goes directly to the LLM provider. We never store it.</p>
            <div style={{ marginBottom:14 }}>
              <label style={{ display:'block', fontSize:11, fontWeight:700, letterSpacing:'0.08em', textTransform:'uppercase', color:'var(--text-3)', marginBottom:6 }}>Provider</label>
              <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                {BYOK_PROVIDERS.map((p,i) => (
                  <button key={i} onClick={() => { setByokProvider(i); if(p.model) setByokModel(p.model) }}
                    style={{ padding:'6px 14px', borderRadius:20, fontSize:12, fontWeight:600, cursor:'pointer', fontFamily:'Inter,sans-serif',
                      background: byokProvider===i ? 'var(--text)' : 'var(--surface)',
                      color: byokProvider===i ? 'var(--bg)' : 'var(--text-2)',
                      border: '1px solid var(--border-strong)', transition:'all 0.15s' }}>
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
            {byokProvider === BYOK_PROVIDERS.length - 1 && (
              <div style={{ marginBottom:14 }}>
                <label style={{ display:'block', fontSize:11, fontWeight:700, letterSpacing:'0.08em', textTransform:'uppercase', color:'var(--text-3)', marginBottom:6 }}>Model</label>
                <input value={byokModel} onChange={e => setByokModel(e.target.value)}
                  placeholder="e.g. openai/gpt-4o"
                  style={{ width:'100%', background:'var(--surface)', border:'1px solid var(--border)', borderRadius:8, color:'var(--text)', fontFamily:'Inter,sans-serif', fontSize:13, padding:'9px 12px', outline:'none', boxSizing:'border-box' }} />
              </div>
            )}
            <div style={{ marginBottom:20 }}>
              <label style={{ display:'block', fontSize:11, fontWeight:700, letterSpacing:'0.08em', textTransform:'uppercase', color:'var(--text-3)', marginBottom:6 }}>API Key</label>
              <input type="password" value={byokKey} onChange={e => setByokKey(e.target.value)}
                placeholder={BYOK_PROVIDERS[byokProvider]?.ph || 'Your API key'}
                style={{ width:'100%', background:'var(--surface)', border:'1px solid var(--border)', borderRadius:8, color:'var(--text)', fontFamily:'Inter,sans-serif', fontSize:13, padding:'9px 12px', outline:'none', boxSizing:'border-box' }} />
            </div>
            <div style={{ display:'flex', gap:8 }}>
              <button onClick={() => {
                const model = byokProvider === BYOK_PROVIDERS.length - 1 ? byokModel : BYOK_PROVIDERS[byokProvider].model
                localStorage.setItem('byok_key', byokKey)
                localStorage.setItem('byok_model', model)
                setByokOpen(false)
              }} style={{ flex:1, padding:'10px', borderRadius:10, fontSize:13, fontWeight:700, cursor:'pointer', fontFamily:'Inter,sans-serif', background:'var(--text)', color:'var(--bg)', border:'none' }}>
                Save
              </button>
              {localStorage.getItem('byok_key') && (
                <button onClick={() => {
                  localStorage.removeItem('byok_key')
                  localStorage.removeItem('byok_model')
                  setByokKey(''); setByokModel(''); setByokOpen(false)
                }} style={{ padding:'10px 16px', borderRadius:10, fontSize:13, fontWeight:600, cursor:'pointer', fontFamily:'Inter,sans-serif', background:'var(--surface)', color:'var(--text-2)', border:'1px solid var(--border-strong)' }}>
                  Remove
                </button>
              )}
            </div>
          </div>
        </div>
      )}

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

const GREETINGS = {
  dawn: [
    { g: 'Good morning.', s: 'The day is yours. Make it count.' },
    { g: 'Early bird.', s: 'Most people are still asleep. You\'re already here.' },
    { g: 'Up before the world.', s: 'This is the time that separates the serious ones.' },
    { g: 'Good morning.', s: 'Fresh start. Fresh thinking.' },
    { g: 'Rise and build.', s: 'The best work happens before the noise begins.' },
  ],
  morning: [
    { g: 'Good morning.', s: 'What are you working on today?' },
    { g: 'Morning.', s: 'Let\'s make today useful.' },
    { g: 'Good morning.', s: 'Something on your mind? Let\'s get into it.' },
    { g: 'Hey, good morning.', s: 'You showed up. That\'s already a win.' },
    { g: 'Morning energy.', s: 'Channel it. Talk to me.' },
  ],
  afternoon: [
    { g: 'Good afternoon.', s: 'Midday check-in. How\'s the momentum?' },
    { g: 'Afternoon.', s: 'Still going strong?' },
    { g: 'Good afternoon.', s: 'What\'s been on your mind since this morning?' },
    { g: 'Hey there.', s: 'Deep work hours. Let\'s not waste them.' },
    { g: 'Good afternoon.', s: 'Half the day done. What matters now?' },
  ],
  evening: [
    { g: 'Good evening.', s: 'How did today go?' },
    { g: 'Evening.', s: 'Time to reflect. What happened today?' },
    { g: 'Good evening.', s: 'The best ideas come at this hour.' },
    { g: 'Hey, good evening.', s: 'Wind down or keep building — you decide.' },
    { g: 'Good evening.', s: 'What did you learn today?' },
  ],
  night: [
    { g: 'Hey, night owl.', s: 'Late night thinking hits different. Let\'s capture it.' },
    { g: 'Still up?', s: 'The best clarity comes when the world goes quiet.' },
    { g: 'Burning the midnight oil.', s: 'I\'m here. Talk to me.' },
    { g: 'Late night mode.', s: 'What\'s keeping you up?' },
    { g: 'Hey.', s: 'It\'s late. Something must be on your mind.' },
  ],
}

function EmptyState() {
  const h = new Date().getHours()
  const bucket = h >= 5 && h < 9 ? 'dawn' : h >= 9 && h < 12 ? 'morning' : h >= 12 && h < 17 ? 'afternoon' : h >= 17 && h < 21 ? 'evening' : 'night'
  const options = GREETINGS[bucket]
  const { g, s } = options[Math.floor(Math.random() * options.length)]
  return (
    <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8, pointerEvents: 'none' }}>
      <p style={{ fontSize: 18, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--text)' }}>{g}</p>
      <p style={{ fontSize: 14, color: 'var(--text-3)', textAlign: 'center', maxWidth: 260, lineHeight: 1.6 }}>{s}</p>
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
