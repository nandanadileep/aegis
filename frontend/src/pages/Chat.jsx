import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getSupabase, authHeaders } from '../lib/supabase'
import { API } from '../lib/api'
import styles from './Chat.module.css'

const BYOK_PROVIDERS = [
  { label: 'Groq',      model: 'groq/llama-3.3-70b-versatile',  ph: 'gsk_...' },
  { label: 'OpenAI',    model: 'openai/gpt-4o',                  ph: 'sk-...' },
  { label: 'Anthropic', model: 'anthropic/claude-sonnet-4-6',    ph: 'sk-ant-...' },
  { label: 'Custom',    model: '',                                ph: 'API key' },
]

export default function Chat() {
  const navigate = useNavigate()
  const [session, setSession] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [byokOpen, setByokOpen] = useState(false)
  const [byokProvider, setByokProvider] = useState(0)
  const [byokModel, setByokModel] = useState('')
  const [byokKey, setByokKey] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef(null)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    if (!menuOpen) return
    function onDown(e) { if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false) }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [menuOpen])

  useEffect(() => {
    let cancel = false
    getSupabase().then(sb => {
      sb.auth.getSession().then(({ data: { session: s } }) => {
        if (!s) { window.location.href = '/login'; return }
        if (!cancel) setSession(s)
        sb.auth.onAuthStateChange((_e, ns) => { if (!ns) window.location.href = '/login'; else setSession(ns) })
      })
    }).catch(() => { window.location.href = '/login' })
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

    try {
      const res = await fetch(`${API}/api/chat`, { method: 'POST', headers: authHeaders(session), body: JSON.stringify({ message: text }) })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Server error')
      setMessages(m => [...m.filter(x => x.role !== 'thinking'), {
        role: 'assistant',
        text: data.reply || 'No response',
        addedNodes: data.added_nodes || [],
      }])
    } catch (e) {
      setMessages(m => [...m.filter(x => x.role !== 'thinking'), { role: 'assistant', text: `Error: ${e.message}` }])
    } finally {
      setSending(false)
      inputRef.current?.focus()
    }
  }

  async function newChat() {
    try {
      await fetch(`${API}/api/clear-history`, { method: 'POST', headers: authHeaders(session) })
    } catch {}
    setMessages([])
    inputRef.current?.focus()
  }

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <div className={styles.menuWrap} ref={menuRef}>
          <button onClick={() => setMenuOpen(o => !o)} className={styles.menuTrigger}>+</button>
          {menuOpen && (
            <div className={styles.menuDropdown}>
              <MenuItem label="New chat" onClick={() => { newChat(); setMenuOpen(false) }} />
              <MenuItem label={byokKey ? 'API Key (set)' : 'API Key'} onClick={() => { setByokOpen(true); setMenuOpen(false) }} />
              <MenuItem label="Import" onClick={() => { navigate('/onboarding?import=true'); setMenuOpen(false) }} />
              <div className={styles.menuDivider} />
              <ThemeMenuItem />
              <div className={styles.menuDivider} />
              <MenuItem label="Sign out" onClick={() => { signOut(); setMenuOpen(false) }} danger />
            </div>
          )}
        </div>
      </header>

      <div className={styles.navToggle}>
        <Link to="/chat" className={`${styles.navToggleBtn} ${styles.navToggleBtnActive}`}>Chat</Link>
        <Link to="/memory" className={styles.navToggleBtn}>Graph</Link>
      </div>

      {byokOpen && (
        <div
          className={styles.modalOverlay}
          onClick={e => { if (e.target === e.currentTarget) setByokOpen(false) }}
        >
          <div className={styles.modalBox}>
            <h3 className={styles.modalTitle}>API Key</h3>
            <p className={styles.modalSub}>Keys go directly to the provider. Not stored on our servers.</p>
            <div className={styles.modalFieldGroup}>
              <label className={styles.modalLabel}>Provider</label>
              <div className={styles.providerBtns}>
                {BYOK_PROVIDERS.map((p, i) => (
                  <button
                    key={i}
                    onClick={() => { setByokProvider(i); if (p.model) setByokModel(p.model) }}
                    className={`${styles.providerBtn} ${byokProvider === i ? styles.providerBtnActive : styles.providerBtnInactive}`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
            {byokProvider === BYOK_PROVIDERS.length - 1 && (
              <div className={styles.modalFieldGroup}>
                <label className={styles.modalLabel}>Model</label>
                <input
                  value={byokModel}
                  onChange={e => setByokModel(e.target.value)}
                  placeholder="e.g. openai/gpt-4o"
                  className={styles.modalInput}
                />
              </div>
            )}
            <div className={styles.modalApiKeyGroup}>
              <label className={styles.modalLabel}>API Key</label>
              <input
                type="password"
                value={byokKey}
                onChange={e => setByokKey(e.target.value)}
                placeholder={BYOK_PROVIDERS[byokProvider]?.ph || 'Your API key'}
                className={styles.modalInput}
              />
            </div>
            <div className={styles.modalActions}>
              <button
                onClick={() => {
                  const model = byokProvider === BYOK_PROVIDERS.length - 1 ? byokModel : BYOK_PROVIDERS[byokProvider].model
                  localStorage.setItem('byok_key', byokKey)
                  localStorage.setItem('byok_model', model)
                  setByokModel(model)
                  setByokOpen(false)
                }}
                className={styles.modalSaveBtn}
              >
                Save
              </button>
              {byokKey && (
                <button
                  onClick={() => {
                    localStorage.removeItem('byok_key')
                    localStorage.removeItem('byok_model')
                    setByokKey(''); setByokModel(''); setByokOpen(false)
                  }}
                  className={styles.modalRemoveBtn}
                >
                  Remove
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      <div className={styles.messages}>
        {messages.length === 0 && <EmptyState />}
        {messages.length > 0 && <div className={styles.messageSpacer} />}
        {messages.map((m, i) => <Message key={i} msg={m} />)}
        <div ref={bottomRef} />
      </div>

      <div className={styles.inputArea}>
        <div className={styles.inputBox}>
          <input
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') sendMessage() }}
            placeholder="say something"
            autoComplete="off"
            className={styles.inputField}
          />
          <button
            onClick={sendMessage}
            disabled={sending || !input.trim()}
            className={`${styles.sendBtn} ${sending ? styles.sendBtnSending : styles.sendBtnReady}`}
          >↑</button>
        </div>
      </div>
    </div>
  )
}

function EmptyState() {
  return (
    <div className={styles.emptyState}>
      <div className={styles.emptyStateInner}>
        <p className={styles.emptyStateSub}>say something</p>
      </div>
    </div>
  )
}

function Message({ msg }) {
  if (msg.role === 'thinking') {
    return (
      <div className={styles.thinkingRow}>
        <div className={styles.thinkingInner}>
          <ThinkingDots />
        </div>
      </div>
    )
  }
  const isUser = msg.role === 'user'
  const learned = !isUser && msg.addedNodes?.length > 0 ? msg.addedNodes : null
  return (
    <div className={`${styles.messageRow} ${isUser ? styles.messageRowUser : styles.messageRowAssistant}`}>
      <div
        className={`${styles.bubble} ${isUser ? styles.bubbleUser : styles.bubbleAssistant}`}
        dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.text) }}
      />
      {learned && (
        <div className={styles.learned}>
          {learned.map((n, i) => (
            <span key={i} className={styles.learnedChip}>{n.key || n.value}</span>
          ))}
        </div>
      )}
    </div>
  )
}

function ThinkingDots() {
  return (
    <span className={styles.td}><span>●</span><span>●</span><span>●</span></span>
  )
}

function renderMarkdown(text) {
  return text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\*\*([^*\n][\s\S]*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`\n]+)`/g, '<code style="font-family:monospace;font-size:0.88em;background:rgba(255,255,255,0.08);padding:1px 5px;border-radius:4px">$1</code>')
}

function MenuItem({ label, onClick, danger }) {
  return (
    <button onClick={onClick} className={`${styles.menuItem} ${danger ? styles.menuItemDanger : ''}`}>
      {label}
    </button>
  )
}

function ThemeMenuItem() {
  const [theme, setTheme] = useState(() => localStorage.getItem('identiti-theme') || 'dark')
  function toggle() { const n = theme === 'dark' ? 'light' : 'dark'; localStorage.setItem('identiti-theme', n); document.documentElement.setAttribute('data-theme', n); setTheme(n) }
  return (
    <button onClick={toggle} className={styles.menuItem}>
      {theme === 'dark' ? 'Light mode' : 'Dark mode'}
    </button>
  )
}