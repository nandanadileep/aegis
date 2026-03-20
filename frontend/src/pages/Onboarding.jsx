import { useEffect, useRef, useState } from 'react'
import { getSupabase, authHeaders } from '../lib/supabase'
import ThemeToggle from '../components/ThemeToggle'
import styles from './Onboarding.module.css'

export default function Onboarding() {
  const [screen, setScreen] = useState('welcome')
  const [session, setSession] = useState(null)
  const [autoUsername, setAutoUsername] = useState('')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [nodeCount, setNodeCount] = useState(0)
  const [turnCount, setTurnCount] = useState(0)
  const [importJson, setImportJson] = useState('')
  const [importErr, setImportErr] = useState('')
  const [importing, setImporting] = useState(false)
  const chatHistory = useRef([])
  const fromChat = useRef(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('import') === 'true') { setScreen('import1'); fromChat.current = true }
    getSupabase().then(sb => {
      sb.auth.getSession().then(async ({ data: { session: s } }) => {
        if (!s) { window.location.href = '/login'; return }
        setSession(s)
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

  async function startChat() {
    if (!session) return
    const res = await fetch('/api/me', { headers: { Authorization: `Bearer ${session.access_token}` } })
    const d = await res.json()
    if (d.exists) { window.location.href = '/chat'; return }
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
      setTurnCount(c => c + 1)
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
      if (data.node_count) setNodeCount(data.node_count)
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

  async function importProfile() {
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
    const html = await resp.text()
    const url = URL.createObjectURL(new Blob([html], { type: 'text/html' }))
    window.open(url, '_blank')
  }

  if (screen === 'welcome') return <WelcomeScreen onBuild={startChat} onImport={() => setScreen('import1')} />
  if (screen === 'chat') return <ChatScreen messages={messages} input={input} setInput={setInput} onSend={() => input.trim() && sendOnboard(input.trim())} sending={sending} inputRef={inputRef} bottomRef={bottomRef} onBack={() => setScreen('welcome')} nodeCount={nodeCount} turnCount={turnCount} />
  if (screen === 'import1') return <Import1Screen onBack={() => fromChat.current ? window.location.href = '/chat' : setScreen('welcome')} onNext={() => setScreen('import2')} />
  if (screen === 'import2') return <Import2Screen value={importJson} onChange={setImportJson} onBack={() => setScreen('import1')} onImport={importProfile} importing={importing} error={importErr} />
  if (screen === 'success') return <SuccessScreen onGraph={() => window.location.href = '/memory'} onCard={downloadCard} />
  return null
}

function WelcomeScreen({ onBuild, onImport }) {
  return (
    <div className={styles.welcomeRoot}>
      <Blobs />
      <div className={styles.themeToggleCorner}><ThemeToggle /></div>
      <div className={styles.welcomeMain}>
        <div className={styles.welcomeCard}>
          <h1 className={styles.welcomeHeading}>Identiti.</h1>
          <p className={styles.welcomeSub}>Your context is with you.</p>
          <div className={styles.cardGrid}>
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
      className={styles.card}
      style={{
        background: hover ? 'var(--surface-hover)' : 'var(--surface)',
        border: `1px solid ${hover ? 'var(--border-strong)' : 'var(--border)'}`,
        transform: hover ? 'translateY(-3px)' : 'none',
      }}
    >
      <div className={styles.cardIcon}>{icon}</div>
      <div className={styles.cardTitle}>{title}</div>
      <div className={styles.cardDesc}>{desc}</div>
    </div>
  )
}

function ChatScreen({ messages, input, setInput, onSend, sending, inputRef, bottomRef, onBack, nodeCount, turnCount }) {
  const TARGET = 10
  const progress = nodeCount >= TARGET ? 1 : nodeCount > 0 ? nodeCount / TARGET : Math.min(0.85, turnCount / 12)
  const displayCount = nodeCount > 0 ? nodeCount : Math.min(TARGET - 1, Math.floor(turnCount * 1.1))
  const done = nodeCount >= TARGET

  return (
    <div className={styles.chatRoot}>
      <Blobs opacity={0.04} />
      <div className={styles.themeToggleCorner}><ThemeToggle /></div>
      <header className={styles.chatHeader}>
        <button onClick={onBack} className={styles.backBtn}>←</button>
        <span className={styles.chatTitle}>Building your profile</span>
        <div className={styles.chatProgress}>
          <ProgressRing progress={progress} count={displayCount} target={TARGET} done={done} />
        </div>
      </header>
      <div className={styles.chatMessages}>
        {messages.map((m, i) => <MsgBubble key={i} msg={m} />)}
        <div ref={bottomRef} />
      </div>
      <div className={styles.inputArea}>
        <div className={styles.inputBox}>
          <input
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') onSend() }}
            placeholder="Type a message…"
            autoComplete="off"
            className={styles.inputField}
          />
          <button
            onClick={onSend}
            disabled={sending || !input.trim()}
            className={`${styles.sendBtn} ${sending ? styles.sendBtnSending : styles.sendBtnReady}`}
          >↑</button>
        </div>
      </div>
    </div>
  )
}

function MsgBubble({ msg }) {
  if (msg.role === 'thinking') return (
    <div className={styles.msgRow}>
      <div className={styles.msgThinkingInner}>
        <span className={styles.td}><span>●</span><span>●</span><span>●</span></span>
      </div>
    </div>
  )
  const isUser = msg.role === 'user'
  return (
    <div className={`${styles.msgRow} ${isUser ? styles.msgRowUser : styles.msgRowAssistant}`}>
      <div className={`${styles.bubble} ${isUser ? styles.bubbleUser : styles.bubbleAssistant}`}>{msg.text}</div>
    </div>
  )
}

function Import1Screen({ onBack, onNext }) {
  const [copied, setCopied] = useState(false)
  const promptText = `Look through everything you know about me — your stored memories, past conversations, preferences, context you've picked up over time. Then output a JSON profile based only on what you actually know. No guessing.`
  const jsonBlock = `{\n  "name": "",\n  "description": "one sentence — who this person is",\n  "values": [],\n  "skills": [],\n  "personality": [],\n  "goals": [],\n  "speaking_style": "",\n  "known_for": []\n}`
  const promptFull = `${promptText}\n\n\`\`\`json\n${jsonBlock}\n\`\`\`\n\nOnly include fields where you have real information. Leave arrays empty if unsure. Output the JSON block only, no explanation.`
  function copy() { navigator.clipboard.writeText(promptFull).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2200) }) }
  return (
    <ImportLayout onBack={onBack} step="Step 1 of 2" title="Export your memory" sub="Copy this into ChatGPT or Claude — any AI that knows you. Paste back the JSON it gives you.">
      <div className={styles.promptBox}>
        <p className={styles.promptText}>{promptText}</p>
        <pre className={styles.promptCode}>{jsonBlock}</pre>
        <p className={styles.promptText} style={{ marginBottom: 0 }}>Only include fields where you have real information. Leave arrays empty if unsure. Output the JSON block only, no explanation.</p>
      </div>
      <div className={styles.import1Actions}>
        <Btn onClick={copy}>{copied ? 'Copied ✓' : 'Copy prompt'}</Btn>
        <BtnFill onClick={onNext}>I have it →</BtnFill>
      </div>
    </ImportLayout>
  )
}

function Import2Screen({ value, onChange, onBack, onImport, importing, error }) {
  return (
    <ImportLayout onBack={onBack} step="Step 2 of 2" title="Paste what it gave you" sub="Drop the memory export below. We'll parse it automatically.">
      <textarea
        value={value}
        onChange={e => onChange(e.target.value)}
        rows={10}
        placeholder='Paste your memory export here…'
        className={styles.importTextarea}
      />
      <BtnFill onClick={onImport} disabled={importing}>{importing ? 'Importing…' : 'Import'}</BtnFill>
      {error && <p className={styles.importError}>{error}</p>}
    </ImportLayout>
  )
}

function ImportLayout({ onBack, step, title, sub, children }) {
  return (
    <div className={styles.importRoot}>
      <Blobs opacity={0.04} />
      <div className={styles.themeToggleCorner}><ThemeToggle /></div>
      <div className={styles.importInner}>
        <button onClick={onBack} className={styles.importBackBtn}>← Back</button>
        <p className={styles.importStepLabel}>{step}</p>
        <h2 className={styles.importTitle}>{title}</h2>
        <p className={styles.importSub}>{sub}</p>
        {children}
      </div>
    </div>
  )
}

function SuccessScreen({ onGraph, onCard }) {
  return (
    <div className={styles.successRoot}>
      <Blobs />
      <div className={styles.successInner}>
        <h2 className={styles.successHeading}>Your profile is built.</h2>
        <p className={styles.successSub}>Your profile is live in the graph. Download your Memory Card and paste it into any AI.</p>
        <div className={styles.successActions}>
          <Btn onClick={onGraph}>View graph</Btn>
          <BtnFill onClick={onCard}>Download Memory Card</BtnFill>
        </div>
      </div>
    </div>
  )
}

function Blobs({ opacity = 0.55 }) {
  return (
    <div
      className={styles.blobs}
      style={{
        background: `radial-gradient(ellipse 70% 60% at 15% 50%, rgba(255,107,53,${opacity}) 0%, transparent 70%), radial-gradient(ellipse 50% 70% at 85% 25%, rgba(34,211,238,${opacity * 0.85}) 0%, transparent 65%), radial-gradient(ellipse 40% 50% at 50% 85%, rgba(225,29,72,${opacity * 0.7}) 0%, transparent 60%)`,
      }}
    />
  )
}

function Btn({ onClick, children, disabled }) {
  return (
    <button onClick={onClick} disabled={disabled} className={styles.btn}>{children}</button>
  )
}

function BtnFill({ onClick, children, disabled }) {
  return (
    <button onClick={onClick} disabled={disabled} className={styles.btnFill}>{children}</button>
  )
}

function ProgressRing({ progress, count, target, done }) {
  const r = 13
  const circ = 2 * Math.PI * r
  const offset = circ * (1 - Math.min(1, progress))
  return (
    <svg width="40" height="40" className={styles.progressRingSvg}>
      <circle cx="20" cy="20" r={r} fill="none" stroke="var(--border)" strokeWidth="2.5" />
      <circle
        cx="20" cy="20" r={r} fill="none"
        stroke={done ? 'var(--text)' : 'var(--text-2)'}
        strokeWidth="2.5"
        strokeDasharray={circ}
        strokeDashoffset={offset}
        strokeLinecap="round"
        style={{ transform: 'rotate(-90deg)', transformOrigin: 'center', transition: 'stroke-dashoffset 0.6s ease' }}
      />
      <text x="20" y="24" textAnchor="middle" fontSize="9" fill="var(--text-2)" fontWeight="700" fontFamily="Inter,sans-serif">
        {count}/{target}
      </text>
    </svg>
  )
}
