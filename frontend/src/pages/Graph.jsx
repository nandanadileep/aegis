import { useEffect, useRef, useState, useCallback } from 'react'
import { getSupabase } from '../lib/supabase'
import { API } from '../lib/api'
import initGraph from '../lib/graphEngine'
import styles from './Graph.module.css'

const SI = ({ children }) => (
  <svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className={styles.siIcon}>
    {children}
  </svg>
)

export default function Graph() {
  const [session, setSession] = useState(null)
  const canvasRef = useRef(null)
  const graphRef  = useRef(null)
  const [stats, setStats] = useState({ nodes: 0, edges: 0 })
  const [showLabels, setShowLabels] = useState(false)
  const [pending, setPending] = useState({ nodes:{}, edges:{}, deletedNodes:[], deletedEdges:[] })
  const [selectedNode, setSelectedNode] = useState(null)
  const [selectedEdge, setSelectedEdge] = useState(null)
  const [searchQ, setSearchQ] = useState('')
  const [searchResults, setSearchResults] = useState(null)
  const [modal, setModal] = useState(null)
  const [confirmDialog, setConfirmDialog] = useState(null)
  const [nodeForm, setNodeForm] = useState({ label:'', name:'', props:'' })
  const [edgeForm, setEdgeForm] = useState({ from:'', type:'', to:'' })
  const [editNodeName, setEditNodeName] = useState('')
  const [graphLoading, setGraphLoading] = useState(true)
  const sessionRef = useRef(null)
  const pendingRef = useRef(pending)
  pendingRef.current = pending
  const autoNodeCreated = useRef(false)

  useEffect(() => {
    getSupabase().then(sb => {
      sb.auth.getSession().then(({ data: { session: s } }) => {
        if (!s) { window.location.href = '/login'; return }
        setSession(s); sessionRef.current = s
        sb.auth.onAuthStateChange((_e, ns) => { if (!ns) window.location.href='/login'; else { setSession(ns); sessionRef.current = ns } })
      })
    })
  }, [])

  useEffect(() => {
    if (!session || !canvasRef.current) return
    const g = initGraph(canvasRef.current, sessionRef, setStats, setPending, setSelectedNode, setSelectedEdge, setGraphLoading, API)
    graphRef.current = g
    g.start()
    return () => g.destroy()
  }, [session])

  useEffect(() => {
    if (graphLoading || stats.nodes > 0 || autoNodeCreated.current || !session) return
    autoNodeCreated.current = true
    const meta = session.user?.user_metadata || {}
    const name = meta.full_name || meta.name || session.user?.email?.split('@')[0] || 'You'
    fetch(`${API}/api/import`, { method:'POST', headers:authH(), body:JSON.stringify({ twin: { name } }) })
      .then(r => r.json())
      .then(data => { if (data.status === 'ok') graphRef.current?.reload() })
  }, [graphLoading, stats.nodes, session])

  function authH() {
    return { 'Content-Type':'application/json', 'Authorization':`Bearer ${sessionRef.current?.access_token}` }
  }

  async function signOut() {
    const sb = await getSupabase()
    try { await sb.auth.signOut() } catch {}
    window.location.href = '/login'
  }

  function runSearch() {
    if (!searchQ.trim()) { setSearchResults(null); graphRef.current?.clearHighlight(); return }
    const q = searchQ.toLowerCase()
    const g = graphRef.current
    if (!g) return
    const deleted = new Set(pendingRef.current.deletedNodes.map(String))
    const deletedEdges = new Set(pendingRef.current.deletedEdges.map(String))
    const matchedNodes = g.getAllNodes().filter(n => !deleted.has(String(n.id)) && ((n._label||'').toLowerCase().includes(q)||(n.title||'').toLowerCase().includes(q)))
    const matchedEdges = g.getAllEdges().filter(e => !deletedEdges.has(String(e.id)) && (e.label||'').toLowerCase().includes(q))
    g.setHighlight(new Set(matchedNodes.map(n=>String(n.id))))
    setSearchResults({ nodes: matchedNodes, edges: matchedEdges })
  }

  async function doAddNode() {
    const { label, name, props: propsStr } = nodeForm
    if (!label||!name) { alert('Label and Name required'); return }
    let props = {}
    if (propsStr) { try { props = JSON.parse(propsStr) } catch { alert('Invalid JSON'); return } }
    const resp = await fetch(`${API}/api/nodes`, { method:'POST', headers:authH(), body:JSON.stringify({ label, name, properties:props }) })
    const data = await resp.json()
    if (!resp.ok) { alert(data.error || data.detail || 'Failed to create node'); return }
    graphRef.current?.addNode(String(data.id), name, data.label || label)
    setPending(p => ({ ...p, nodes: { ...p.nodes, [data.id]:{ type:'add', label, name } } }))
    setStats(s => ({ ...s, nodes: s.nodes+1 }))
    setModal(null)
  }

  async function doAddEdge() {
    const { from, type, to } = edgeForm
    if (!from||!type||!to) { alert('All fields required'); return }
    const resp = await fetch(`${API}/api/relationships`, { method:'POST', headers:authH(), body:JSON.stringify({ from, type, to }) })
    if (!resp.ok) { alert('Failed'); return }
    const data = await resp.json()
    graphRef.current?.addEdge(String(data.id), from, to, type)
    setPending(p => ({ ...p, edges: { ...p.edges, [data.id]:{ type:'add', relType:type } } }))
    setModal(null)
  }

  function doDeleteNode() {
    if (!selectedNode) return
    const g = graphRef.current
    const removed = g?.deleteNode(selectedNode) || []
    setStats(s => ({ ...s, nodes: s.nodes-1, edges: s.edges - removed.length }))
    setPending(p => ({ ...p, deletedNodes:[...p.deletedNodes,selectedNode], deletedEdges:[...p.deletedEdges,...removed] }))
    setSelectedNode(null)
    setSearchResults(r => r ? {
      nodes: r.nodes.filter(n => String(n.id) !== String(selectedNode)),
      edges: r.edges.filter(e => !removed.includes(String(e.id))),
    } : null)
  }

  function doDeleteEdge() {
    if (!selectedEdge) return
    graphRef.current?.deleteEdge(selectedEdge)
    setStats(s => ({ ...s, edges: s.edges-1 }))
    setPending(p => ({ ...p, deletedEdges:[...p.deletedEdges,selectedEdge] }))
    setSelectedEdge(null)
    setSearchResults(r => r ? { ...r, edges: r.edges.filter(e => String(e.id) !== String(selectedEdge)) } : null)
  }

  async function doCommit() {
    const resp = await fetch(`${API}/api/commit`, { method:'POST', headers:authH(), body:JSON.stringify(pendingRef.current) })
    if (!resp.ok) { alert('Commit failed'); return }
    setPending({ nodes:{}, edges:{}, deletedNodes:[], deletedEdges:[] })
    graphRef.current?.reload(authH)
    setModal(null)
  }

  function doReset() {
    setConfirmDialog({
      message: 'Discard all pending changes?',
      hint: 'This cannot be undone.',
      danger: true,
      onConfirm: () => {
        setPending({ nodes:{}, edges:{}, deletedNodes:[], deletedEdges:[] })
        graphRef.current?.reload(authH)
      }
    })
  }

  async function doEditNode() {
    const name = editNodeName.trim()
    if (!name || !selectedNode) return
    const resp = await fetch(`${API}/api/nodes/${selectedNode}`, { method:'PATCH', headers:authH(), body:JSON.stringify({ name }) })
    if (!resp.ok) { alert('Failed to rename node'); return }
    graphRef.current?.renameNode(selectedNode, name)
    setModal(null)
  }

  async function doDeduplicateGraph() {
    setMenuOpen(false)
    const resp = await fetch(`${API}/api/deduplicate`, { method:'POST', headers:authH() })
    const data = await resp.json()
    if (!resp.ok) { alert('Dedup failed'); return }
    graphRef.current?.reload(authH)
    setStats(s => ({ ...s, nodes: Math.max(0, s.nodes - (data.deleted || 0)) }))
  }

  async function downloadWallet() {
    const resp = await fetch(`${API}/api/wallet`, { headers:authH() })
    const html = await resp.text()
    const url = URL.createObjectURL(new Blob([html], { type: 'text/html' }))
    window.open(url, '_blank')
  }

  const SHAPES = ['octopus','jellyfish','fish','whale','starfish','butterfly','heart','bird','spiral','snowflake','flower','tree','snake','crescent','diamond','ring','galaxy','dna','cross','infinity','crown','mountain','wave']
  const [shapeIdx, setShapeIdx] = useState(-1)
  const activeShape = shapeIdx >= 0 ? SHAPES[shapeIdx] : null
  function applyShape(idx) { setShapeIdx(idx); graphRef.current?.setShape(idx >= 0 ? SHAPES[idx] : null) }
  function nextShape() { applyShape((shapeIdx + 1) % SHAPES.length) }
  function prevShape() { applyShape(shapeIdx <= 0 ? SHAPES.length - 1 : shapeIdx - 1) }

  const [tourOpen, setTourOpen] = useState(() => !localStorage.getItem('identiti-tour-done'))
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef(null)
  useEffect(() => {
    if (!menuOpen) return
    function onDown(e) { if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false) }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [menuOpen])

  const pendingCount = Object.keys(pending.nodes).length + Object.keys(pending.edges).length + pending.deletedNodes.length + pending.deletedEdges.length
  const selectedNodeData = selectedNode && graphRef.current?.getNode(selectedNode)
  const selectedEdgeData = selectedEdge && graphRef.current?.getEdge(selectedEdge)

  const TYPE_COLORS = { 'Person':'#2997ff','Skill':'#30d158','Value':'#ff9f0a','Goal':'#ff375f','Trait':'#bf5af2','Identity':'#64d2ff','Project':'#ffd60a','Behavior':'#ff6961','Constraint':'#ac8e68','Belief':'#32ade6' }
  function typeColor(t) {
    if (TYPE_COLORS[t]) return TYPE_COLORS[t]
    let h = 0; for (let i = 0; i < t.length; i++) h = (h * 31 + t.charCodeAt(i)) & 0xffff
    return `hsl(${h % 360},80%,62%)`
  }

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.brand}>Identiti</span>
        </div>

        <div className={styles.headerRight}>
          <div className={styles.menuWrap} ref={menuRef}>
            <button onClick={() => setMenuOpen(o => !o)} className={styles.menuTrigger}>···</button>
            {menuOpen && (
              <div className={styles.menuDropdown}>
                <MenuItem label="Download Memory Card" icon="⬇" onClick={() => { downloadWallet(); setMenuOpen(false) }} />
                <MenuItem label="Clean up duplicates" icon="✦" onClick={doDeduplicateGraph} />
                <div className={styles.menuDivider} />
                <ThemeMenuItem />
                <div className={styles.menuDivider} />
                <MenuItem label="Sign out" icon="→" onClick={() => { signOut(); setMenuOpen(false) }} danger />
              </div>
            )}
          </div>
        </div>
      </header>

      <div className={styles.navToggle}>
        <a href="/chat" className={styles.navToggleBtn}>Chat</a>
        <a href="/memory" className={`${styles.navToggleBtn} ${styles.navToggleBtnActive}`}>Graph</a>
        <button className={styles.sidebarToggleBtn} onClick={() => setSidebarOpen(o => !o)}>≡</button>
      </div>

      <div className={styles.body}>
        <div className={styles.canvasWrap}>
          <canvas ref={canvasRef} className={styles.canvas} />
          {graphLoading && (
            <div className={styles.loadingOverlay}>
              <div className={styles.spinner} />
            </div>
          )}
          {!graphLoading && stats.nodes === 0 && (
            <div className={styles.emptyGraphHint}>
              <p className={styles.emptyGraphText}>Add nodes and relationships to see the graph</p>
            </div>
          )}
          {!graphLoading && stats.nodes > 0 && stats.nodes < 20 && (
            <div className={styles.nodeHint}>
              {20 - stats.nodes} more nodes and the shapes get interesting
            </div>
          )}
        </div>

        {sidebarOpen && <div className={styles.sidebarBackdrop} onClick={() => setSidebarOpen(false)} />}
        <div className={`${styles.sidebar} ${sidebarOpen ? styles.sidebarOpen : ''}`}>
          <div className={styles.sidebarHandle} onClick={() => setSidebarOpen(false)} />
          <div className={styles.searchWrap}>
            <button
              className={`${styles.eyeBtn} ${showLabels ? styles.eyeBtnOn : ''}`}
              onClick={() => { const next = !showLabels; setShowLabels(next); graphRef.current?.setShowLabels(next) }}
              title={showLabels ? 'Hide labels' : 'Show labels'}
            >
              {showLabels ? (
                <svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M1 10s3.5-6 9-6 9 6 9 6-3.5 6-9 6-9-6-9-6z"/><circle cx="10" cy="10" r="2.5"/></svg>
              ) : (
                <svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M1 10s3.5-6 9-6 9 6 9 6-3.5 6-9 6-9-6-9-6z"/><circle cx="10" cy="10" r="2.5"/><line x1="2" y1="2" x2="18" y2="18"/></svg>
              )}
            </button>
            <input
              value={searchQ}
              onChange={e => setSearchQ(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') runSearch()
                if (e.key === 'Escape') { setSearchQ(''); setSearchResults(null); graphRef.current?.clearHighlight() }
              }}
              placeholder="Search nodes & relationships…"
              className={styles.searchInput}
            />
            {searchQ && (
              <button
                className={styles.searchClear}
                onClick={() => { setSearchQ(''); setSearchResults(null); graphRef.current?.clearHighlight() }}
              >×</button>
            )}
          </div>
          <Section label="Graph">
            <StatRow k="Nodes" v={stats.nodes} />
            <StatRow k="Relationships" v={stats.edges} />
          </Section>

          {searchResults && (
            <Section label="Search Results">
              <div className={styles.searchResultsScroll}>
                {searchResults.nodes.length === 0 && searchResults.edges.length === 0 && (
                  <p className={styles.searchResultEmpty}>No results</p>
                )}
                {searchResults.nodes.map(n => (
                  <div
                    key={n.id}
                    onClick={() => { setSelectedNode(String(n.id)); setSelectedEdge(null); graphRef.current?.focusNode(String(n.id)) }}
                    className={styles.searchResultItem}
                  >
                    <span className={styles.searchResultName}>{n._label || n.label}</span>
                    <span className={styles.searchResultType}>{n.title || 'node'}</span>
                  </div>
                ))}
                {searchResults.edges.map(e => {
                  const fn = graphRef.current?.getNode(String(e.from)), tn = graphRef.current?.getNode(String(e.to))
                  return (
                    <div
                      key={e.id}
                      onClick={() => { setSelectedEdge(e.id); setSelectedNode(null) }}
                      className={styles.searchResultItem}
                    >
                      <span className={styles.searchResultName}>{fn?._label || e.from} → {tn?._label || e.to}</span>
                      <span className={styles.searchResultType}>{e.label}</span>
                    </div>
                  )
                })}
              </div>
            </Section>
          )}

          {selectedNodeData && (
            <Section label="Node">
              <DR k="Name" v={selectedNodeData._label || selectedNodeData.label || '—'} />
              {selectedNodeData.title && (
                <DR k="Type" v={<span style={{ color: typeColor(selectedNodeData.title) }}>{selectedNodeData.title}</span>} />
              )}
              <div className={styles.detailActions}>
                <button
                  className={`${styles.btn} ${styles.btnFlex}`}
                  onClick={() => { setEditNodeName(selectedNodeData._label || selectedNodeData.label || ''); setModal('editNode') }}
                >Edit</button>
                <button
                  className={`${styles.btn} ${styles.btnDanger} ${styles.btnFlex}`}
                  onClick={doDeleteNode}
                >Delete</button>
              </div>
            </Section>
          )}

          {selectedEdgeData && (
            <Section label="Relationship">
              <DR k="Type" v={selectedEdgeData.label || '—'} />
              <DR k="From" v={graphRef.current?.getNode(String(selectedEdgeData.from))?._label || selectedEdgeData.from} />
              <DR k="To" v={graphRef.current?.getNode(String(selectedEdgeData.to))?._label || selectedEdgeData.to} />
              <div className={styles.detailActionsEdge}>
                <button
                  className={`${styles.btn} ${styles.btnDanger} ${styles.btnFull}`}
                  onClick={doDeleteEdge}
                >Delete Relationship</button>
              </div>
            </Section>
          )}

          <Section label="Add">
            <div className={styles.addBtns}>
              <button
                className={`${styles.btn} ${styles.btnFull}`}
                onClick={() => { setNodeForm({ label:'', name:'', props:'' }); setModal('addNode') }}
              >+ Node</button>
              <button
                className={`${styles.btn} ${styles.btnFull}`}
                onClick={() => { setEdgeForm({ from: selectedNode || '', type:'', to:'' }); setModal('addEdge') }}
              >+ Relationship</button>
            </div>
          </Section>

          <div className={styles.shapeStrip}>
            <div className={styles.shapeStripTrack}>
              {[...SHAPES, ...SHAPES].map((s, i) => (
                <button
                  key={i}
                  onClick={() => applyShape(activeShape === s ? -1 : SHAPES.indexOf(s))}
                  className={`${styles.shapeChip} ${activeShape === s ? styles.shapeChipActive : ''}`}
                  title={s}
                >
                  <ShapeIcon shape={s} />
                </button>
              ))}
            </div>
          </div>

          {pendingCount > 0 && (
            <Section label="Pending">
              <div className={styles.pendingScroll}>
                {Object.entries(pending.nodes).map(([id, c]) => <ChangeItem key={id} text={`+ Node: ${c.name}`} />)}
                {Object.entries(pending.edges).map(([id, c]) => <ChangeItem key={id} text={`+ Rel: ${c.relType}`} />)}
                {pending.deletedNodes.map(id => <ChangeItem key={id} text={`− Node: ${id}`} del />)}
                {pending.deletedEdges.map(id => <ChangeItem key={id} text={`− Rel: ${id}`} del />)}
              </div>
              <div className={styles.pendingActions}>
                <button
                  className={`${styles.btn} ${styles.btnFlex} ${styles.btnCommit}`}
                  onClick={() => setModal('commit')}
                >Commit</button>
                <button
                  className={`${styles.btn} ${styles.btnFlex} ${styles.btnRevert}`}
                  onClick={doReset}
                >Revert</button>
              </div>
            </Section>
          )}
        </div>
      </div>

      {modal && (
        <div
          onClick={e => { if (e.target === e.currentTarget) setModal(null) }}
          className={styles.modalOverlay}
        >
          <div className={styles.modalBox}>
            {modal === 'addNode' && <>
              <h3 className={styles.modalTitle}>Add Node</h3>
              <p className={styles.modalSub}>Create a new node and link it to your profile.</p>
              <MInput label="Label" placeholder="Skill, Value, Goal…" value={nodeForm.label} onChange={v => setNodeForm(f => ({ ...f, label: v }))} />
              <MInput label="Name" placeholder="e.g. Python, Discipline…" value={nodeForm.name} onChange={v => setNodeForm(f => ({ ...f, name: v }))} />
              <MInput label='Properties (JSON, optional)' placeholder='{"level":"expert"}' value={nodeForm.props} onChange={v => setNodeForm(f => ({ ...f, props: v }))} textarea />
              <div className={styles.modalActions}>
                <button className={`${styles.btn} ${styles.btnFlex}`} onClick={() => setModal(null)}>Cancel</button>
                <button className={`${styles.btn} ${styles.btnPrimary} ${styles.btnFlex}`} onClick={doAddNode}>Add Node</button>
              </div>
            </>}
            {modal === 'addEdge' && <>
              <h3 className={styles.modalTitle}>Add Relationship</h3>
              <p className={styles.modalSub}>Connect two nodes with a relationship.</p>
              <MInput label="From (node ID)" placeholder="node-id" value={edgeForm.from} onChange={v => setEdgeForm(f => ({ ...f, from: v }))} />
              <MInput label="Relationship Type" placeholder="HAS_SKILL, HOLDS_VALUE…" value={edgeForm.type} onChange={v => setEdgeForm(f => ({ ...f, type: v }))} />
              <MInput label="To (node ID)" placeholder="node-id" value={edgeForm.to} onChange={v => setEdgeForm(f => ({ ...f, to: v }))} />
              <div className={styles.modalActions}>
                <button className={`${styles.btn} ${styles.btnFlex}`} onClick={() => setModal(null)}>Cancel</button>
                <button className={`${styles.btn} ${styles.btnPrimary} ${styles.btnFlex}`} onClick={doAddEdge}>Add</button>
              </div>
            </>}
            {modal === 'editNode' && <>
              <h3 className={styles.modalTitle}>Edit Node Name</h3>
              <MInput label="Name" placeholder="New name…" value={editNodeName} onChange={setEditNodeName} />
              <div className={styles.modalActions}>
                <button className={`${styles.btn} ${styles.btnFlex}`} onClick={() => setModal(null)}>Cancel</button>
                <button className={`${styles.btn} ${styles.btnPrimary} ${styles.btnFlex}`} onClick={doEditNode}>Save</button>
              </div>
            </>}
            {modal === 'commit' && <>
              <h3 className={styles.modalTitle}>Confirm Changes</h3>
              <p className={styles.modalSub}>The following changes will be saved to the graph:</p>
              <div className={styles.commitScroll}>
                {Object.entries(pending.nodes).map(([id, c]) => <ChangeItem key={id} text={`+ Add node: ${c.name}`} />)}
                {Object.entries(pending.edges).map(([id, c]) => <ChangeItem key={id} text={`+ Add rel: ${c.relType}`} />)}
                {pending.deletedNodes.map(id => <ChangeItem key={id} text="− Remove node" del />)}
                {pending.deletedEdges.map(id => <ChangeItem key={id} text="− Remove rel" del />)}
              </div>
              <div className={styles.modalActions}>
                <button className={`${styles.btn} ${styles.btnFlex}`} onClick={() => setModal(null)}>Cancel</button>
                <button className={`${styles.btn} ${styles.btnPrimary} ${styles.btnFlex}`} onClick={doCommit}>Confirm & Save</button>
              </div>
            </>}
          </div>
        </div>
      )}

      <button
        className={styles.tourBtn}
        onClick={() => setTourOpen(true)}
        title="Quick tour"
      >?</button>

      {tourOpen && <Tour onClose={() => { localStorage.setItem('identiti-tour-done', '1'); setTourOpen(false) }} />}

      {confirmDialog && (
        <div
          onClick={e => { if (e.target === e.currentTarget) setConfirmDialog(null) }}
          className={styles.confirmOverlay}
        >
          <div className={styles.confirmBox}>
            <p className={`${styles.confirmMsg} ${confirmDialog.hint ? styles.confirmMsgWithHint : styles.confirmMsgNoHint}`}>
              {confirmDialog.message}
            </p>
            {confirmDialog.hint && <p className={styles.confirmHint}>{confirmDialog.hint}</p>}
            <div className={styles.confirmActions}>
              <button className={`${styles.btn} ${styles.btnFlex}`} onClick={() => setConfirmDialog(null)}>Cancel</button>
              <button
                className={`${styles.btn} ${styles.btnFlex} ${styles.confirmActionBtn} ${confirmDialog.danger ? styles.confirmActionBtnDanger : styles.confirmActionBtnNormal}`}
                onClick={() => { confirmDialog.onConfirm(); setConfirmDialog(null) }}
              >
                {confirmDialog.danger ? 'Delete' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function MenuItem({ label, icon, onClick, disabled, danger }) {
  return (
    <button
      onClick={disabled ? undefined : onClick}
      className={`${styles.menuItem} ${danger ? styles.menuItemDanger : ''} ${disabled ? styles.menuItemDisabled : ''}`}
      style={disabled ? { opacity: 0.4 } : undefined}
    >
      <span className={styles.menuIcon}>{icon}</span>{label}
    </button>
  )
}

function ThemeMenuItem() {
  const [theme, setTheme] = useState(() => localStorage.getItem('identiti-theme') || 'dark')
  function toggle() { const n = theme === 'dark' ? 'light' : 'dark'; localStorage.setItem('identiti-theme', n); document.documentElement.setAttribute('data-theme', n); setTheme(n) }
  return (
    <button onClick={toggle} className={styles.menuItem}>
      <span className={styles.menuIconSvg}>
        {theme === 'dark' ? (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
            <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
            <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
            <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
          </svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
          </svg>
        )}
      </span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}
    </button>
  )
}

function Section({ label, children }) {
  return (
    <div className={styles.section}>
      <div className={styles.sectionLabel}>{label}</div>
      {children}
    </div>
  )
}

function StatRow({ k, v }) {
  return (
    <div className={styles.statRow}>
      <span className={styles.statKey}>{k}</span>
      <span className={styles.statVal}>{v}</span>
    </div>
  )
}

function DR({ k, v }) {
  return (
    <div className={styles.dr}>
      <span className={styles.drKey}>{k}</span>
      <span className={styles.drVal}>{v}</span>
    </div>
  )
}

function ChangeItem({ text, del }) {
  return (
    <div className={`${styles.changeItem} ${del ? styles.changeItemDel : styles.changeItemAdd}`}>{text}</div>
  )
}

function MInput({ label, placeholder, value, onChange, textarea }) {
  return (
    <div className={styles.minputWrap}>
      <label className={styles.minputLabel}>{label}</label>
      {textarea
        ? <textarea value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} className={`${styles.minputField} ${styles.minputTextarea}`} />
        : <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} className={styles.minputField} />
      }
    </div>
  )
}

function ShapeIcon({ shape }) {
  const icons = {
    heart:     <path d="M8 13C3 10 2 7 2 5.5a3 3 0 0 1 6-1 3 3 0 0 1 6 1c0 1.5-1 4.5-6 7.5z" fill="currentColor" stroke="none"/>,
    diamond:   <polygon points="8,1.5 14,8 8,14.5 2,8"/>,
    ring:      <circle cx="8" cy="8" r="5" strokeWidth="2.5"/>,
    cross:     <><line x1="8" y1="2" x2="8" y2="14"/><line x1="2" y1="8" x2="14" y2="8"/></>,
    infinity:  <path d="M4.5 8c0-1.7 1.2-2.5 2.5-2.5 1.5 0 2 2.5 2 2.5s.5 2.5 2 2.5 2.5-.8 2.5-2.5-1.2-2.5-2.5-2.5c-1.5 0-2 2.5-2 2.5s-.5-2.5-2-2.5S2.5 6.3 2.5 8z"/>,
    crown:     <><polyline points="2.5,12 4,7 7,10 8,4 9,10 12,7 13.5,12"/><line x1="2.5" y1="12" x2="13.5" y2="12"/></>,
    snowflake: <><line x1="8" y1="1.5" x2="8" y2="14.5"/><line x1="1.5" y1="8" x2="14.5" y2="8"/><line x1="3" y1="3" x2="13" y2="13"/><line x1="13" y1="3" x2="3" y2="13"/></>,
    wave:      <path d="M1 8c2-4 3-4 4.5 0s2.5 4 4 0 2.5-4 4 0"/>,
    mountain:  <polyline points="1.5,14 6,5 9,10 11.5,5 14.5,14"/>,
    flower:    <><ellipse cx="8" cy="3.5" rx="1.5" ry="2.5"/><ellipse cx="8" cy="12.5" rx="1.5" ry="2.5"/><ellipse cx="3.5" cy="8" rx="2.5" ry="1.5"/><ellipse cx="12.5" cy="8" rx="2.5" ry="1.5"/><circle cx="8" cy="8" r="2.5" fill="currentColor" stroke="none"/></>,
    tree:      <><polygon points="8,2 14,13 2,13"/><line x1="8" y1="13" x2="8" y2="15" strokeWidth="2"/></>,
    fish:      <><ellipse cx="7" cy="8" rx="4" ry="2.5"/><polyline points="11,5.5 14.5,8 11,10.5"/><circle cx="5.5" cy="7.5" r="0.7" fill="currentColor" stroke="none"/></>,
    bird:      <path d="M2 10c3-6 6-5.5 7.5-3C11 5 13.5 5 15 6c-2 .5-3.5 2-4 4.5C9 9 6 9 2 10z"/>,
    galaxy:    <path d="M8 8c3-1 5 0 5 1.5s-3.5 3.5-8 2.5-4-4-1-5 7-1 6 2.5-4 4-7 2-2-5 2-5 5 1 4.5 4"/>,
    dna:       <><path d="M5.5 2c0 4.5 5 6.5 5 10.5"/><path d="M10.5 2c0 4.5-5 6.5-5 10.5"/><line x1="6" y1="5.5" x2="10" y2="5.5"/><line x1="6" y1="8" x2="10" y2="8"/><line x1="6" y1="10.5" x2="10" y2="10.5"/></>,
    butterfly: <><path d="M8 8.5c-1-3.5-3.5-4-5-3S2 8 3.5 9.5 8 8.5 8 8.5z"/><path d="M8 8.5c1-3.5 3.5-4 5-3s1 2.5-.5 4S8 8.5 8 8.5z"/><path d="M8 8.5c-1 2 -3 2.5-4 2S2.5 9.5 3.5 9.5 8 8.5 8 8.5z"/><path d="M8 8.5c1 2 3 2.5 4 2s1-1.5 0-1.5-4 1-4 1z"/><line x1="8" y1="6" x2="8" y2="13"/></>,
    whale:     <><path d="M2 8.5c0 0 2.5-4.5 7-3.5s5 3 4.5 4.5-2.5 2-5.5 1.5S2 8.5 2 8.5z"/><polyline points="13.5,6.5 15.5,4.5 13.5,9.5"/></>,
    jellyfish: <><path d="M3.5 8C3.5 5 5.5 3 8 3s4.5 2 4.5 5"/><path d="M5.5 8c-.5 3-1 5-1.5 5.5"/><line x1="8" y1="8" x2="8" y2="14"/><path d="M10.5 8c.5 3 1 5 1.5 5.5"/></>,
    octopus:   <><circle cx="8" cy="6" r="3.5"/><path d="M4.5 9c-.5 3-1.5 4.5-1.5 5"/><path d="M6.5 9.5c0 3-.5 4 0 4.5"/><line x1="8" y1="9.5" x2="8" y2="14"/><path d="M9.5 9.5c0 3 .5 4 0 4.5"/><path d="M11.5 9c.5 3 1.5 4.5 1.5 5"/></>,
    starfish:  <polygon points="8,1 9.5,6.5 15,6.5 10.5,9.5 12.5,15 8,12 3.5,15 5.5,9.5 1,6.5 6.5,6.5"/>,
    snake:     <path d="M2 13c2.5.5 4-1.5 3.5-3.5S3 5.5 5 4.5s4 .5 4 2.5-1.5 4.5.5 5.5 4.5-1 4-3.5"/>,
    crescent:  <path d="M10.5 13A5.5 5.5 0 0 1 10.5 3a5.5 5.5 0 0 0 0 10z" fill="currentColor" stroke="none"/>,
    spiral:    <path d="M8 8c0 0 .5-2 2-2s2 1.5 2 3-1.5 3-3 3-4-2-4-4.5S7.5 3 10 3s6 2.5 6 6"/>,
  }
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      {icons[shape]}
    </svg>
  )
}

const TOUR_STEPS = [
  {
    title: 'Your memory graph',
    desc: 'Every dot is a piece of you — a skill, goal, value, or trait. The lines show how everything connects.',
  },
  {
    title: 'Search your graph',
    desc: 'Type anything in the search bar to instantly find and highlight matching nodes and relationships.',
    hint: 'Try searching a skill or your name',
  },
  {
    title: 'Add nodes & relationships',
    desc: 'Use + Node and + Relationship to manually add anything to your graph. Hit Commit to save.',
  },
  {
    title: 'Select, edit, or delete',
    desc: 'Click any node on the canvas to select it. Rename or delete it from the panel on the right.',
  },
  {
    title: 'Download your Memory Card',
    desc: 'Open ··· in the top-right corner to download your Memory Card — paste it into any AI to give it full context about you.',
  },
  {
    title: 'Now try something fun',
    desc: 'Pick any icon in the strip below Add. Your nodes will rearrange into that shape.',
    hint: 'Try a crown, a galaxy, or a spiral ✦',
  },
]

function Tour({ onClose }) {
  const [step, setStep] = useState(0)
  const s = TOUR_STEPS[step]
  const isLast = step === TOUR_STEPS.length - 1
  return (
    <div className={styles.tourCard}>
      <div className={styles.tourTop}>
        <span className={styles.tourCounter}>{step + 1} / {TOUR_STEPS.length}</span>
        <button className={styles.tourClose} onClick={onClose}>×</button>
      </div>
      <h3 className={styles.tourTitle}>{s.title}</h3>
      <p className={styles.tourDesc}>{s.desc}</p>
      {s.hint && <p className={styles.tourHint}>{s.hint}</p>}
      <div className={styles.tourDots}>
        {TOUR_STEPS.map((_, i) => (
          <div key={i} className={`${styles.tourDot} ${i === step ? styles.tourDotActive : ''}`} onClick={() => setStep(i)} />
        ))}
      </div>
      <div className={styles.tourActions}>
        {step > 0 && (
          <button className={styles.tourPrev} onClick={() => setStep(s => s - 1)}>←</button>
        )}
        <button
          className={styles.tourNext}
          onClick={() => isLast ? onClose() : setStep(s => s + 1)}
        >
          {isLast ? 'Got it ✓' : 'Next →'}
        </button>
      </div>
    </div>
  )
}
