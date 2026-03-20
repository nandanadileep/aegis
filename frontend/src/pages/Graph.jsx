import { useEffect, useRef, useState, useCallback } from 'react'
import { getSupabase } from '../lib/supabase'

// ── Shared button styles ──
const S = {
  btn: { display:'inline-flex',alignItems:'center',gap:5,padding:'7px 14px',borderRadius:40,fontSize:13,fontWeight:600,cursor:'pointer',border:'1px solid var(--border-strong)',background:'var(--bg)',color:'var(--text)',fontFamily:'Inter,sans-serif',transition:'all .15s',whiteSpace:'nowrap',letterSpacing:'-0.01em' },
  btnPrimary: { background:'var(--text)',border:'none',color:'var(--bg)' },
}

const SHAPE_COLORS = {
  octopus:  {fill:'#9b5de5',glow:'rgba(155,93,229,0.8)'},
  jellyfish:{fill:'#f15bb5',glow:'rgba(241,91,181,0.8)'},
  fish:     {fill:'#00b4d8',glow:'rgba(0,180,216,0.8)'},
  whale:    {fill:'#0077b6',glow:'rgba(0,119,182,0.8)'},
  starfish: {fill:'#f77f00',glow:'rgba(247,127,0,0.8)'},
  butterfly:{fill:'#e040fb',glow:'rgba(224,64,251,0.8)'},
  heart:    {fill:'#e63946',glow:'rgba(230,57,70,0.8)'},
  bird:     {fill:'#74c0fc',glow:'rgba(116,192,252,0.8)'},
  spiral:   {fill:'#2ec4b6',glow:'rgba(46,196,182,0.8)'},
  snowflake:{fill:'#a8dadc',glow:'rgba(168,218,220,0.8)'},
  flower:   {fill:'#ff6b9d',glow:'rgba(255,107,157,0.8)'},
  tree:     {fill:'#52b788',glow:'rgba(82,183,136,0.8)'},
  snake:    {fill:'#6a994e',glow:'rgba(106,153,78,0.8)'},
  crescent: {fill:'#f4d03f',glow:'rgba(244,208,63,0.8)'},
  diamond:  {fill:'#00f5d4',glow:'rgba(0,245,212,0.8)'},
}

const SHAPE_STRIP = [
  {icon:'🐙',shape:'octopus',label:'Octopus'},
  {icon:'🪼',shape:'jellyfish',label:'Jellyfish'},
  {icon:'🐟',shape:'fish',label:'Fish'},
  {icon:'🐋',shape:'whale',label:'Whale'},
  {icon:'⭐',shape:'starfish',label:'Starfish'},
  {icon:'🦋',shape:'butterfly',label:'Butterfly'},
  {icon:'❤️',shape:'heart',label:'Heart'},
  {icon:'🦅',shape:'bird',label:'Eagle'},
  {icon:'🌀',shape:'spiral',label:'Spiral'},
  {icon:'❄️',shape:'snowflake',label:'Snowflake'},
  {icon:'🌸',shape:'flower',label:'Flower'},
  {icon:'🌲',shape:'tree',label:'Tree'},
  {icon:'🐍',shape:'snake',label:'Snake'},
  {icon:'🌙',shape:'crescent',label:'Crescent'},
  {icon:'💎',shape:'diamond',label:'Diamond'},
  {icon:'🦈',shape:'fish',label:'Shark'},
  {icon:'🦑',shape:'octopus',label:'Squid'},
  {icon:'🐬',shape:'fish',label:'Dolphin'},
  {icon:'🕊️',shape:'bird',label:'Dove'},
  {icon:'🐠',shape:'fish',label:'Clownfish'},
  {icon:'🦜',shape:'bird',label:'Parrot'},
  {icon:'🐳',shape:'whale',label:'Humpback'},
  {icon:'☀️',shape:'snowflake',label:'Sun'},
  {icon:'🦀',shape:'starfish',label:'Crab'},
  {icon:'🌺',shape:'flower',label:'Hibiscus'},
  {icon:'🎯',shape:'spiral',label:'Target'},
  {icon:'🦚',shape:'flower',label:'Peacock'},
  {icon:'🐡',shape:'fish',label:'Puffer'},
  {icon:'🦢',shape:'bird',label:'Swan'},
  {icon:'🦭',shape:'whale',label:'Seal'},
  {icon:'🌟',shape:'starfish',label:'Starburst'},
  {icon:'🐉',shape:'snake',label:'Dragon'},
  {icon:'🦋',shape:'butterfly',label:'Moth'},
]

export default function Graph() {
  const [session, setSession] = useState(null)
  const canvasRef = useRef(null)
  const graphRef  = useRef(null) // holds all graph state
  const [stats, setStats] = useState({ nodes: 0, edges: 0 })
  const [pending, setPending] = useState({ nodes:{}, edges:{}, deletedNodes:[], deletedEdges:[] })
  const [selectedNode, setSelectedNode] = useState(null)
  const [selectedEdge, setSelectedEdge] = useState(null)
  const [searchQ, setSearchQ] = useState('')
  const [searchResults, setSearchResults] = useState(null)
  const [modal, setModal] = useState(null) // null | 'addNode' | 'addEdge' | 'commit'
  const [shapeMode, setShapeMode] = useState(null)
  const [confirmDialog, setConfirmDialog] = useState(null) // { message, onConfirm, danger? }
  const [nodeForm, setNodeForm] = useState({ label:'', name:'', props:'' })
  const [edgeForm, setEdgeForm] = useState({ from:'', type:'', to:'' })
  const sessionRef = useRef(null)
  const pendingRef = useRef(pending)
  pendingRef.current = pending

  // ── Auth ──
  useEffect(() => {
    getSupabase().then(sb => {
      sb.auth.getSession().then(({ data: { session: s } }) => {
        if (!s) { window.location.href = '/login'; return }
        setSession(s); sessionRef.current = s
        sb.auth.onAuthStateChange((_e, ns) => { if (!ns) window.location.href='/login'; else { setSession(ns); sessionRef.current = ns } })
      })
    })
  }, [])

  // ── Canvas init ──
  useEffect(() => {
    if (!session || !canvasRef.current) return
    const g = initGraph(canvasRef.current, sessionRef, setStats, setPending, setSelectedNode, setSelectedEdge)
    graphRef.current = g
    g.start()
    return () => g.destroy()
  }, [session])

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
    const matchedNodes = g.getAllNodes().filter(n => (n._label||'').toLowerCase().includes(q)||(n.title||'').toLowerCase().includes(q))
    const matchedEdges = g.getAllEdges().filter(e => (e.label||'').toLowerCase().includes(q))
    g.setHighlight(new Set(matchedNodes.map(n=>String(n.id))))
    setSearchResults({ nodes: matchedNodes, edges: matchedEdges })
  }

  async function doAddNode() {
    const { label, name, props: propsStr } = nodeForm
    if (!label||!name) { alert('Label and Name required'); return }
    let props = {}
    if (propsStr) { try { props = JSON.parse(propsStr) } catch { alert('Invalid JSON'); return } }
    const resp = await fetch('/api/nodes', { method:'POST', headers:authH(), body:JSON.stringify({ label, name, properties:props }) })
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
    const resp = await fetch('/api/relationships', { method:'POST', headers:authH(), body:JSON.stringify({ from, type, to }) })
    if (!resp.ok) { alert('Failed'); return }
    const data = await resp.json()
    graphRef.current?.addEdge(String(data.id), from, to, type)
    setPending(p => ({ ...p, edges: { ...p.edges, [data.id]:{ type:'add', relType:type } } }))
    setModal(null)
  }

  function doDeleteNode() {
    if (!selectedNode) return
    const g = graphRef.current
    const n = g?.getNode(selectedNode)
    setConfirmDialog({
      message: `Delete "${n?._label||selectedNode}"?`,
      hint: 'This will also remove all its relationships.',
      danger: true,
      onConfirm: () => {
        const removed = g?.deleteNode(selectedNode) || []
        setStats(s => ({ ...s, nodes: s.nodes-1, edges: s.edges - removed.length }))
        setPending(p => ({ ...p, deletedNodes:[...p.deletedNodes,selectedNode], deletedEdges:[...p.deletedEdges,...removed] }))
        setSelectedNode(null)
      }
    })
  }

  function doDeleteEdge() {
    if (!selectedEdge) return
    const e = graphRef.current?.getEdge(selectedEdge)
    setConfirmDialog({
      message: `Delete relationship "${e?.label||selectedEdge}"?`,
      danger: true,
      onConfirm: () => {
        graphRef.current?.deleteEdge(selectedEdge)
        setStats(s => ({ ...s, edges: s.edges-1 }))
        setPending(p => ({ ...p, deletedEdges:[...p.deletedEdges,selectedEdge] }))
        setSelectedEdge(null)
      }
    })
  }

  async function doCommit() {
    const resp = await fetch('/api/commit', { method:'POST', headers:authH(), body:JSON.stringify(pendingRef.current) })
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

  async function downloadWallet() {
    const resp = await fetch('/api/wallet', { headers:authH() })
    const blob = await resp.blob()
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download='twin_card.md'; a.click()
    URL.revokeObjectURL(a.href)
  }

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
    <div style={{ display:'flex', flexDirection:'column', height:'100vh', background:'var(--bg)', overflow:'hidden' }}>
      {/* Header */}
      <header style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'0 20px', height:56, borderBottom:'1px solid var(--border)', flexShrink:0, background:'var(--bg)', zIndex:50 }}>
        {/* Left: brand + nav */}
        <div style={{ display:'flex', alignItems:'center', gap:16 }}>
          <span style={{ fontSize:15, fontWeight:800, letterSpacing:'-0.03em' }}>Identiti</span>
          <div style={{ display:'flex', gap:1, background:'var(--surface)', borderRadius:10, padding:3, border:'1px solid var(--border)' }}>
            <a href="/chat" style={{ padding:'5px 12px', borderRadius:7, fontSize:13, fontWeight:500, color:'var(--text-2)', textDecoration:'none' }}>Chat</a>
            <a href="/memory" style={{ padding:'5px 12px', borderRadius:7, fontSize:13, fontWeight:600, color:'var(--text)', textDecoration:'none', background:'var(--bg)', boxShadow:'0 1px 3px rgba(0,0,0,0.12)' }}>Graph</a>
          </div>
        </div>

        {/* Right: overflow */}
        <div style={{ display:'flex', gap:8, alignItems:'center' }}>

          {/* ··· menu */}
          <div style={{ position:'relative' }} ref={menuRef}>
            <button onClick={()=>setMenuOpen(o=>!o)} style={{ width:34, height:34, borderRadius:8, background:'var(--surface)', border:'1px solid var(--border)', cursor:'pointer', display:'flex', alignItems:'center', justifyContent:'center', fontSize:16, color:'var(--text-2)', fontFamily:'Inter,sans-serif' }}>···</button>
            {menuOpen && (
              <div style={{ position:'absolute', top:'calc(100% + 8px)', right:0, background:'var(--bg)', border:'1px solid var(--border)', borderRadius:10, padding:6, minWidth:180, boxShadow:'0 8px 24px rgba(0,0,0,0.18)', zIndex:200 }}>
                <MenuItem label="Download Twin Card" icon="⬇" onClick={()=>{ downloadWallet(); setMenuOpen(false) }} />
                <div style={{ height:1, background:'var(--border)', margin:'4px 0' }} />
                <ThemeMenuItem />
                <div style={{ height:1, background:'var(--border)', margin:'4px 0' }} />
                <MenuItem label="Sign out" icon="→" onClick={()=>{ signOut(); setMenuOpen(false) }} danger />
              </div>
            )}
          </div>
        </div>
      </header>

      <div style={{ display:'flex', flex:1, overflow:'hidden' }}>
        {/* Canvas */}
        <div style={{ flex:1, position:'relative', background:'var(--surface-2)', overflow:'hidden', borderRight:'1px solid var(--border)' }}>
          <canvas ref={canvasRef} style={{ width:'100%', height:'100%', display:'block', cursor:'grab' }} />
        </div>

        {/* Sidebar */}
        <div style={{ width:280, flexShrink:0, background:'var(--bg)', borderLeft:'1px solid var(--border)', display:'flex', flexDirection:'column', overflowY:'auto' }}>
          <div style={{ padding:'14px 16px', borderBottom:'1px solid var(--border)' }}>
            <input value={searchQ} onChange={e=>setSearchQ(e.target.value)}
              onKeyDown={e=>{ if(e.key==='Enter') runSearch(); if(e.key==='Escape'){setSearchQ('');setSearchResults(null);graphRef.current?.clearHighlight()} }}
              placeholder="Search nodes & relationships…"
              style={{ width:'100%', background:'var(--surface)', border:'1px solid var(--border)', borderRadius:8, color:'var(--text)', fontFamily:'Inter,sans-serif', fontSize:13, padding:'8px 12px', outline:'none' }} />
          </div>
          <Section label="Graph">
            <StatRow k="Nodes" v={stats.nodes} />
            <StatRow k="Relationships" v={stats.edges} />
          </Section>

          <Section label="Shape">
            <style>{`
              @keyframes shapeTicker { from { transform:translateX(0) } to { transform:translateX(-50%) } }
              .shape-strip:hover { animation-play-state: paused !important; }
            `}</style>
            <div style={{ overflow:'hidden', width:'100%', maskImage:'linear-gradient(to right, transparent, black 12%, black 88%, transparent)', WebkitMaskImage:'linear-gradient(to right, transparent, black 12%, black 88%, transparent)' }}>
              <div className="shape-strip" style={{ display:'flex', gap:4, animation:'shapeTicker 28s linear infinite', width:'max-content' }}>
                {[...SHAPE_STRIP, ...SHAPE_STRIP].map((s,i) => (
                  <button key={i} title={s.label} onClick={() => {
                    if (shapeMode?.shape === s.shape) { setShapeMode(null); graphRef.current?.setShape(null) }
                    else { setShapeMode(s); graphRef.current?.setShape(s.shape) }
                  }}
                    style={{ fontSize:20, background: shapeMode?.shape===s.shape&&i<SHAPE_STRIP.length ? 'var(--surface)' : 'transparent', border:'none', cursor:'pointer', padding:'4px 3px', borderRadius:6, lineHeight:1, flexShrink:0, outline:'none' }}>
                    {s.icon}
                  </button>
                ))}
              </div>
            </div>
          </Section>

          {searchResults && (
            <Section label="Search Results">
              {searchResults.nodes.length===0&&searchResults.edges.length===0 && <p style={{ fontSize:13, color:'var(--text-3)', textAlign:'center', padding:'8px 0' }}>No results</p>}
              {searchResults.nodes.map(n=>(
                <div key={n.id} onClick={()=>{setSelectedNode(String(n.id));setSelectedEdge(null);graphRef.current?.focusNode(String(n.id))}} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'8px 10px', borderRadius:8, cursor:'pointer', marginBottom:4 }} onMouseEnter={e=>e.currentTarget.style.background='var(--surface)'} onMouseLeave={e=>e.currentTarget.style.background='transparent'}>
                  <span style={{ fontSize:13 }}>{n._label||n.label}</span>
                  <span style={{ fontSize:10, textTransform:'uppercase', letterSpacing:'0.06em', color:'var(--text-3)' }}>{n.title||'node'}</span>
                </div>
              ))}
              {searchResults.edges.map(e=>{
                const fn=graphRef.current?.getNode(String(e.from)), tn=graphRef.current?.getNode(String(e.to))
                return <div key={e.id} onClick={()=>{setSelectedEdge(e.id);setSelectedNode(null)}} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'8px 10px', borderRadius:8, cursor:'pointer', marginBottom:4 }} onMouseEnter={el=>el.currentTarget.style.background='var(--surface)'} onMouseLeave={el=>el.currentTarget.style.background='transparent'}>
                  <span style={{ fontSize:13 }}>{fn?._label||e.from} → {tn?._label||e.to}</span>
                  <span style={{ fontSize:10, textTransform:'uppercase', letterSpacing:'0.06em', color:'var(--text-3)' }}>{e.label}</span>
                </div>
              })}
            </Section>
          )}

          {selectedNodeData && (
            <Section label="Node">
              <DR k="Name" v={selectedNodeData._label||selectedNodeData.label||'—'} />
              {selectedNodeData.title && <DR k="Type" v={<span style={{ color:typeColor(selectedNodeData.title) }}>{selectedNodeData.title}</span>} />}
              <div style={{ marginTop:12 }}>
                <button style={{ ...S.btn, background:'#fff1f2', borderColor:'#fecdd3', color:'#e11d48', width:'100%', justifyContent:'center' }} onClick={doDeleteNode}>Delete Node</button>
              </div>
            </Section>
          )}

          {selectedEdgeData && (
            <Section label="Relationship">
              <DR k="Type" v={selectedEdgeData.label||'—'} />
              <DR k="From" v={graphRef.current?.getNode(String(selectedEdgeData.from))?._label||selectedEdgeData.from} />
              <DR k="To" v={graphRef.current?.getNode(String(selectedEdgeData.to))?._label||selectedEdgeData.to} />
              <div style={{ marginTop:12 }}>
                <button style={{ ...S.btn, background:'#fff1f2', borderColor:'#fecdd3', color:'#e11d48', width:'100%', justifyContent:'center' }} onClick={doDeleteEdge}>Delete Relationship</button>
              </div>
            </Section>
          )}

          <Section label="Add">
            <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
              <button style={{ ...S.btn, justifyContent:'center' }} onClick={()=>{ setNodeForm({label:'',name:'',props:''}); setModal('addNode') }}>+ Node</button>
              <button style={{ ...S.btn, justifyContent:'center' }} onClick={()=>{ setEdgeForm({from:selectedNode||'',type:'',to:''}); setModal('addEdge') }}>+ Relationship</button>
            </div>
          </Section>

          {pendingCount > 0 && (
            <Section label="Pending">
              {Object.entries(pending.nodes).map(([id,c])=><ChangeItem key={id} text={`+ Node: ${c.name}`} />)}
              {Object.entries(pending.edges).map(([id,c])=><ChangeItem key={id} text={`+ Rel: ${c.relType}`} />)}
              {pending.deletedNodes.map(id=><ChangeItem key={id} text={`− Node: ${id}`} del />)}
              {pending.deletedEdges.map(id=><ChangeItem key={id} text={`− Rel: ${id}`} del />)}
              <div style={{ display:'flex', gap:6, marginTop:10 }}>
                <button style={{ ...S.btn, flex:1, justifyContent:'center', background:'#0000ee', color:'#fff', border:'none', fontWeight:600 }} onClick={()=>setModal('commit')}>Commit</button>
                <button style={{ ...S.btn, flex:1, justifyContent:'center', color:'var(--text-2)' }} onClick={doReset}>Revert</button>
              </div>
            </Section>
          )}
        </div>
      </div>

      {/* Modals */}
      {modal && (
        <div onClick={e=>{ if(e.target===e.currentTarget) setModal(null) }} style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.5)', backdropFilter:'blur(4px)', display:'flex', alignItems:'center', justifyContent:'center', zIndex:200 }}>
          <div style={{ background:'var(--modal-bg)', border:'1px solid var(--border)', borderRadius:16, padding:28, width:'90%', maxWidth:460, maxHeight:'80vh', overflowY:'auto' }}>
            {modal==='addNode' && <>
              <h3 style={{ fontSize:18, fontWeight:800, letterSpacing:'-0.02em', marginBottom:6 }}>Add Node</h3>
              <p style={{ fontSize:13, color:'var(--text-2)', marginBottom:20, lineHeight:1.5 }}>Create a new node and link it to your profile.</p>
              <MInput label="Label" placeholder="Skill, Value, Goal…" value={nodeForm.label} onChange={v=>setNodeForm(f=>({...f,label:v}))} />
              <MInput label="Name" placeholder="e.g. Python, Discipline…" value={nodeForm.name} onChange={v=>setNodeForm(f=>({...f,name:v}))} />
              <MInput label='Properties (JSON, optional)' placeholder='{"level":"expert"}' value={nodeForm.props} onChange={v=>setNodeForm(f=>({...f,props:v}))} textarea />
              <div style={{ display:'flex', gap:8, marginTop:20 }}>
                <button style={{ ...S.btn, flex:1, justifyContent:'center' }} onClick={()=>setModal(null)}>Cancel</button>
                <button style={{ ...S.btn, ...S.btnPrimary, flex:1, justifyContent:'center' }} onClick={doAddNode}>Add Node</button>
              </div>
            </>}
            {modal==='addEdge' && <>
              <h3 style={{ fontSize:18, fontWeight:800, letterSpacing:'-0.02em', marginBottom:6 }}>Add Relationship</h3>
              <p style={{ fontSize:13, color:'var(--text-2)', marginBottom:20, lineHeight:1.5 }}>Connect two nodes with a relationship.</p>
              <MInput label="From (node ID)" placeholder="node-id" value={edgeForm.from} onChange={v=>setEdgeForm(f=>({...f,from:v}))} />
              <MInput label="Relationship Type" placeholder="HAS_SKILL, HOLDS_VALUE…" value={edgeForm.type} onChange={v=>setEdgeForm(f=>({...f,type:v}))} />
              <MInput label="To (node ID)" placeholder="node-id" value={edgeForm.to} onChange={v=>setEdgeForm(f=>({...f,to:v}))} />
              <div style={{ display:'flex', gap:8, marginTop:20 }}>
                <button style={{ ...S.btn, flex:1, justifyContent:'center' }} onClick={()=>setModal(null)}>Cancel</button>
                <button style={{ ...S.btn, ...S.btnPrimary, flex:1, justifyContent:'center' }} onClick={doAddEdge}>Add</button>
              </div>
            </>}
            {modal==='commit' && <>
              <h3 style={{ fontSize:18, fontWeight:800, letterSpacing:'-0.02em', marginBottom:6 }}>Confirm Changes</h3>
              <p style={{ fontSize:13, color:'var(--text-2)', marginBottom:16, lineHeight:1.5 }}>The following changes will be saved to the graph:</p>
              <div style={{ maxHeight:200, overflowY:'auto', marginBottom:8 }}>
                {Object.entries(pending.nodes).map(([id,c])=><ChangeItem key={id} text={`+ Add node: ${c.name}`} />)}
                {Object.entries(pending.edges).map(([id,c])=><ChangeItem key={id} text={`+ Add rel: ${c.relType}`} />)}
                {pending.deletedNodes.map(id=><ChangeItem key={id} text="− Remove node" del />)}
                {pending.deletedEdges.map(id=><ChangeItem key={id} text="− Remove rel" del />)}
              </div>
              <div style={{ display:'flex', gap:8, marginTop:20 }}>
                <button style={{ ...S.btn, flex:1, justifyContent:'center' }} onClick={()=>setModal(null)}>Cancel</button>
                <button style={{ ...S.btn, ...S.btnPrimary, flex:1, justifyContent:'center' }} onClick={doCommit}>Confirm & Save</button>
              </div>
            </>}
          </div>
        </div>
      )}

      {/* Confirm dialog */}
      {confirmDialog && (
        <div onClick={e=>{ if(e.target===e.currentTarget){ setConfirmDialog(null) } }} style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.6)', backdropFilter:'blur(6px)', display:'flex', alignItems:'center', justifyContent:'center', zIndex:300 }}>
          <div style={{ background:'var(--bg)', border:'1px solid var(--border)', borderRadius:16, padding:28, width:'90%', maxWidth:380, boxShadow:'0 24px 60px rgba(0,0,0,0.4)' }}>
            <p style={{ fontSize:16, fontWeight:700, letterSpacing:'-0.02em', marginBottom: confirmDialog.hint ? 8 : 24 }}>{confirmDialog.message}</p>
            {confirmDialog.hint && <p style={{ fontSize:13, color:'var(--text-2)', marginBottom:24, lineHeight:1.5 }}>{confirmDialog.hint}</p>}
            <div style={{ display:'flex', gap:8 }}>
              <button style={{ ...S.btn, flex:1, justifyContent:'center' }} onClick={()=>setConfirmDialog(null)}>Cancel</button>
              <button
                style={{ ...S.btn, flex:1, justifyContent:'center', border:'none', background: confirmDialog.danger?'#e11d48':'var(--text)', color:'#fff' }}
                onClick={()=>{ confirmDialog.onConfirm(); setConfirmDialog(null) }}
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
    <button onClick={disabled?undefined:onClick} style={{ display:'flex', alignItems:'center', gap:9, width:'100%', padding:'8px 10px', borderRadius:7, border:'none', background:'transparent', cursor:disabled?'not-allowed':'pointer', fontSize:13, fontWeight:500, color:danger?'#e11d48':disabled?'var(--text-3)':'var(--text)', fontFamily:'Inter,sans-serif', textAlign:'left', opacity:disabled?0.4:1 }}>
      <span style={{ opacity:0.6, fontSize:14 }}>{icon}</span>{label}
    </button>
  )
}
function ThemeMenuItem() {
  const [theme, setTheme] = useState(()=>localStorage.getItem('identiti-theme')||'dark')
  function toggle() { const n=theme==='dark'?'light':'dark'; localStorage.setItem('identiti-theme',n); document.documentElement.setAttribute('data-theme',n); setTheme(n) }
  return (
    <button onClick={toggle} style={{ display:'flex', alignItems:'center', gap:9, width:'100%', padding:'8px 10px', borderRadius:7, border:'none', background:'transparent', cursor:'pointer', fontSize:13, fontWeight:500, color:'var(--text)', fontFamily:'Inter,sans-serif', textAlign:'left' }}>
      <span style={{ opacity:0.6, display:'flex', alignItems:'center' }}>
        {theme==='dark' ? (
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
      </span>{theme==='dark'?'Light mode':'Dark mode'}
    </button>
  )
}

function Section({ label, children }) {
  return <div style={{ padding:'20px 18px', borderBottom:'1px solid var(--border)' }}>
    <div style={{ fontSize:10, fontWeight:700, letterSpacing:'0.1em', textTransform:'uppercase', color:'var(--text-3)', marginBottom:12 }}>{label}</div>
    {children}
  </div>
}
function StatRow({ k, v }) {
  return <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'8px 12px', background:'var(--surface)', borderRadius:8, marginBottom:6 }}>
    <span style={{ fontSize:13, color:'var(--text-2)' }}>{k}</span>
    <span style={{ fontSize:13, fontWeight:600 }}>{v}</span>
  </div>
}
function DR({ k, v }) {
  return <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', padding:'7px 0', borderBottom:'1px solid var(--surface)' }}>
    <span style={{ fontSize:12, color:'var(--text-3)' }}>{k}</span>
    <span style={{ fontSize:12, fontWeight:500, textAlign:'right', maxWidth:'60%', wordBreak:'break-word' }}>{v}</span>
  </div>
}
function ChangeItem({ text, del }) {
  return <div style={{ padding:'8px 10px', borderRadius:8, fontSize:12, marginBottom:5, background: del?'rgba(225,29,72,0.1)':'rgba(0,0,238,0.08)', border:`1px solid ${del?'rgba(225,29,72,0.25)':'rgba(0,0,238,0.2)'}` }}>{text}</div>
}
function MInput({ label, placeholder, value, onChange, textarea }) {
  const style = { width:'100%', background:'var(--surface)', border:'1px solid var(--border)', borderRadius:8, color:'var(--text)', fontFamily:'Inter,sans-serif', fontSize:14, padding:'10px 14px', outline:'none', ...(textarea?{resize:'vertical',minHeight:80}:{}) }
  return <div style={{ marginBottom:14 }}>
    <label style={{ display:'block', fontSize:11, fontWeight:700, letterSpacing:'0.08em', textTransform:'uppercase', color:'var(--text-3)', marginBottom:6 }}>{label}</label>
    {textarea ? <textarea value={value} onChange={e=>onChange(e.target.value)} placeholder={placeholder} style={style} /> : <input value={value} onChange={e=>onChange(e.target.value)} placeholder={placeholder} style={style} />}
  </div>
}

// ── Canvas graph engine ──
function initGraph(canvas, sessionRef, setStats, setPending, setSelectedNode, setSelectedEdge) {
  const ctx = canvas.getContext('2d')
  let rafId = null, destroyed = false

  class DS {
    constructor() { this._d = new Map() }
    add(items) { [].concat(items).forEach(i=>{ if(i&&i.id!=null) this._d.set(String(i.id),{...i}) }) }
    remove(id) { this._d.delete(String(id)) }
    get(q) { if(q===undefined) return [...this._d.values()]; if(typeof q==='object'&&q.filter) return [...this._d.values()].filter(q.filter); return this._d.get(String(q))||null }
    getIds() { return [...this._d.keys()] }
    get length() { return this._d.size }
    update(items) { [].concat(items).forEach(i=>{ const ex=this._d.get(String(i.id)); if(ex) this._d.set(String(i.id),{...ex,...i}) }) }
    clear() { this._d.clear() }
  }

  const nodes = new DS(), edges = new DS()
  const animNodes = new Map()
  const cam = { x:0, y:0, scale:1, tx:0, ty:0, ts:1 }
  const mouse = { sx:-9999, sy:-9999, wx:-9999, wy:-9999, radius:130 }
  let dragging=false, dragStartSX=0, dragStartSY=0, camStartX=0, camStartY=0
  let draggedNode=null, dragOffX=0, dragOffY=0, didDrag=false
  let hoveredNode=null, hoveredEdge=null
  let selNode=null, selEdge=null
  let searchHL=new Set()
  let shiftHeld=false
  let zoomTimer=null

  function resize() {
    const r=canvas.parentElement.getBoundingClientRect()
    const dpr=window.devicePixelRatio||1
    canvas.width=r.width*dpr; canvas.height=r.height*dpr
    canvas.style.width=r.width+'px'; canvas.style.height=r.height+'px'
  }
  const ro = new ResizeObserver(resize)
  ro.observe(canvas.parentElement)
  resize()

  function cssW() { return canvas.width/(window.devicePixelRatio||1)||800 }
  function cssH() { return canvas.height/(window.devicePixelRatio||1)||600 }
  function authH() { return { 'Content-Type':'application/json','Authorization':`Bearer ${sessionRef.current?.access_token}` } }
  function sToW(sx,sy) { return { x:(sx-cam.x)/cam.scale, y:(sy-cam.y)/cam.scale } }

  function hitNode(wx,wy) {
    const r=10/cam.scale
    for(const [id,an] of animNodes){ const dx=an.x-wx,dy=an.y-wy; if(dx*dx+dy*dy<r*r) return id }
    return null
  }
  function hitEdge(wx,wy) {
    const th=7/cam.scale
    for(const eid of edges.getIds()){
      const e=edges.get(eid),a=animNodes.get(String(e.from)),b=animNodes.get(String(e.to)); if(!a||!b) continue
      const dx=b.x-a.x,dy=b.y-a.y,l2=dx*dx+dy*dy; if(!l2) continue
      const t=Math.max(0,Math.min(1,((wx-a.x)*dx+(wy-a.y)*dy)/l2))
      const px=a.x+t*dx-wx,py=a.y+t*dy-wy
      if(px*px+py*py<th*th) return eid
    }
    return null
  }

  // 350-iteration force layout with cooling + velocity damping (matches old HTML)
  function computeLayout(nl,el) {
    const W=cssW(),H=cssH()
    const pos=new Map()
    nl.forEach((n,i)=>{
      const a=(i/nl.length)*Math.PI*2, r=Math.min(W,H)*0.3
      pos.set(String(n.id),{ x:W/2+Math.cos(a)*r+(Math.random()-.5)*50, y:H/2+Math.sin(a)*r+(Math.random()-.5)*50, vx:0, vy:0 })
    })
    for(let iter=0;iter<350;iter++){
      const cool=Math.max(0.05,1-iter/250)
      const ids=[...pos.keys()]
      // Repulsion
      for(let i=0;i<ids.length;i++){
        for(let j=i+1;j<ids.length;j++){
          const a=pos.get(ids[i]),b=pos.get(ids[j])
          const dx=a.x-b.x,dy=a.y-b.y,dist=Math.sqrt(dx*dx+dy*dy)||0.1
          const f=(6000/(dist*dist))*cool
          a.vx+=(dx/dist)*f; a.vy+=(dy/dist)*f
          b.vx-=(dx/dist)*f; b.vy-=(dy/dist)*f
        }
      }
      // Spring attraction
      el.forEach(e=>{
        const a=pos.get(String(e.from)),b=pos.get(String(e.to)); if(!a||!b) return
        const dx=b.x-a.x,dy=b.y-a.y,dist=Math.sqrt(dx*dx+dy*dy)||0.1
        const f=(dist-170)*0.006*cool
        a.vx+=(dx/dist)*f; a.vy+=(dy/dist)*f
        b.vx-=(dx/dist)*f; b.vy-=(dy/dist)*f
      })
      // Center gravity
      pos.forEach(p=>{ p.vx+=(W/2-p.x)*0.003; p.vy+=(H/2-p.y)*0.003 })
      // Integrate + dampen
      pos.forEach(p=>{ p.x+=p.vx*0.6; p.y+=p.vy*0.6; p.vx*=0.82; p.vy*=0.82 })
    }
    return pos
  }

  function makeAnimNode(id,x,y) {
    return { x, y, baseX:x, baseY:y, angle:Math.random()*Math.PI*2, av:(Math.random()-.5)*.01, phase:Math.random()*Math.PI*2, ar:10+Math.random()*8 }
  }

  // ── Shape generators — produce exactly n well-defined points ──
  function generateShapePoints(shape, n) {
    const W=cssW(), H=cssH(), cx=W/2, cy=H/2
    const R=Math.min(W,H)*0.32
    const pts=[]

    if (shape==='octopus') {
      // Tight head cluster
      const headN=Math.max(6, Math.floor(n*0.22))
      for(let i=0;i<headN;i++){
        const a=(i/headN)*Math.PI*2, r=R*0.18*(0.4+Math.sqrt(Math.random())*0.6)
        pts.push({ x:cx+Math.cos(a)*r, y:cy-R*0.05+Math.sin(a)*r*0.9 })
      }
      // 8 distinct arms — tight, long, curved
      const armN=n-headN, nArms=8
      for(let arm=0;arm<nArms;arm++){
        const count=arm<armN%nArms ? Math.ceil(armN/nArms) : Math.floor(armN/nArms)
        const baseA=(arm/nArms)*Math.PI*2 - Math.PI/2
        for(let j=0;j<count;j++){
          const t=(j+1)/(count+1)
          const curve=Math.sin(t*Math.PI)*R*0.12*(arm%2===0?1:-1)
          const perp=baseA+Math.PI/2
          pts.push({
            x:cx+Math.cos(baseA)*R*1.15*t + Math.cos(perp)*curve,
            y:cy+Math.sin(baseA)*R*1.15*t + Math.sin(perp)*curve
          })
        }
      }
    } else if (shape==='jellyfish') {
      // Bell — tight dome
      const bellN=Math.floor(n*0.35)
      for(let i=0;i<bellN;i++){
        const a=Math.PI*(0.1+0.8*(i/bellN)) // upper arc only
        const r=R*(0.55+Math.sqrt(Math.random())*0.45)
        pts.push({ x:cx+Math.cos(a)*r, y:cy-R*0.2+Math.sin(a)*r*0.5 })
      }
      // Long straight tentacles
      const tentN=n-bellN, nTent=7
      for(let i=0;i<tentN;i++){
        const ti=i%nTent
        const depth=(Math.floor(i/nTent)+1)/Math.ceil(tentN/nTent)
        const bx=cx+(-0.5+ti/(nTent-1))*R*1.1
        const wave=Math.sin(depth*Math.PI*4+ti)*12
        pts.push({ x:bx+wave, y:cy+R*0.28+depth*R*1.5 })
      }
    } else if (shape==='fish') {
      // Ellipse body
      const bodyN=Math.floor(n*0.72)
      for(let i=0;i<bodyN;i++){
        const a=(i/bodyN)*Math.PI*2
        const taper=0.55+0.45*Math.cos(a) // tapers toward tail
        const r=Math.sqrt(Math.random())*taper
        pts.push({ x:cx-R*0.05+Math.cos(a)*R*0.9*r, y:cy+Math.sin(a)*R*0.42*r })
      }
      // Forked tail
      const tailN=n-bodyN
      for(let i=0;i<tailN;i++){
        const t=Math.random()
        const side=(i<tailN/2?1:-1)
        pts.push({ x:cx+R*0.88+t*R*0.38, y:cy+side*(R*0.06+t*R*0.48) })
      }
    } else if (shape==='whale') {
      // Long tapered body
      const bodyN=Math.floor(n*0.78)
      for(let i=0;i<bodyN;i++){
        const a=(i/bodyN)*Math.PI*2
        const taper=0.4+0.6*Math.abs(Math.cos(a*0.5)) // fatter in middle
        const r=Math.sqrt(Math.random())*taper
        pts.push({ x:cx+Math.cos(a)*R*1.2*r, y:cy+Math.sin(a)*R*0.3*r })
      }
      // Tail flukes — two lobes
      const flukeN=n-bodyN
      for(let i=0;i<flukeN;i++){
        const side=(i<flukeN/2?1:-1)
        const t=Math.random()
        pts.push({ x:cx+R*1.1+t*R*0.3, y:cy+side*(R*0.12+t*R*0.38) })
      }
    } else if (shape==='starfish') {
      // 5 arms radiating cleanly
      const nArms=5, perArm=n/nArms
      for(let arm=0;arm<nArms;arm++){
        const baseA=(arm/nArms)*Math.PI*2-Math.PI/2
        const count=arm<n%nArms?Math.ceil(perArm):Math.floor(perArm)
        for(let j=0;j<count;j++){
          const t=(j+1)/(count+1)
          const spread=R*0.08*(1-t)
          pts.push({
            x:cx+Math.cos(baseA)*R*1.05*t+(Math.random()-.5)*spread*2,
            y:cy+Math.sin(baseA)*R*1.05*t+(Math.random()-.5)*spread*2
          })
        }
      }
    } else if (shape==='butterfly') {
      const bodyN=Math.max(3,Math.floor(n*0.07))
      for(let i=0;i<bodyN;i++) pts.push({ x:cx+(Math.random()-.5)*R*0.08, y:cy-R*0.3+i*(R*0.6/bodyN) })
      const wingN=n-bodyN, pw=Math.floor(wingN/2)
      for(let i=0;i<pw;i++){
        const a=(i/pw)*Math.PI*2, r=Math.sqrt(Math.random())
        const bx=Math.cos(a)*R*0.52*r, by=Math.sin(a)*R*0.35*r
        pts.push({ x:cx-R*0.42+bx*Math.cos(-0.35)-by*Math.sin(-0.35), y:cy-R*0.08+bx*Math.sin(-0.35)+by*Math.cos(-0.35) })
      }
      for(let i=0;i<wingN-pw;i++){
        const a=(i/(wingN-pw))*Math.PI*2, r=Math.sqrt(Math.random())
        const bx=Math.cos(a)*R*0.52*r, by=Math.sin(a)*R*0.35*r
        pts.push({ x:cx+R*0.42+bx*Math.cos(0.35)-by*Math.sin(0.35), y:cy-R*0.08+bx*Math.sin(0.35)+by*Math.cos(0.35) })
      }
    } else if (shape==='heart') {
      for(let i=0;i<n;i++){
        const t=(i/n)*Math.PI*2
        const hx=R*0.65*Math.pow(Math.sin(t),3)
        const hy=-R*0.55*(0.8125*Math.cos(t)-0.3125*Math.cos(2*t)-0.125*Math.cos(3*t)-0.0625*Math.cos(4*t))
        const j=R*0.08*(Math.random()-.5)
        pts.push({ x:cx+hx+j, y:cy+hy+R*0.08+j })
      }
    } else if (shape==='bird') {
      const bodyN=Math.max(3,Math.floor(n*0.08))
      for(let i=0;i<bodyN;i++) pts.push({ x:cx+(Math.random()-.5)*R*0.1, y:cy+(Math.random()-.5)*R*0.1 })
      const wingN=n-bodyN, pw=Math.floor(wingN/2)
      for(let i=0;i<pw;i++){
        const t=(i+1)/(pw+1), arc=Math.sin(t*Math.PI)*R*0.18
        pts.push({ x:cx-R*0.08-t*R*0.92, y:cy-arc-t*R*0.28+(Math.random()-.5)*R*0.06 })
      }
      for(let i=0;i<wingN-pw;i++){
        const t=(i+1)/(wingN-pw+1), arc=Math.sin(t*Math.PI)*R*0.18
        pts.push({ x:cx+R*0.08+t*R*0.92, y:cy-arc-t*R*0.28+(Math.random()-.5)*R*0.06 })
      }
    } else if (shape==='spiral') {
      const turns=3.2, tMax=turns*Math.PI*2
      for(let i=0;i<n;i++){
        const theta=(i/n)*tMax, r=(theta/tMax)*R*1.1
        pts.push({ x:cx+r*Math.cos(theta)+(Math.random()-.5)*R*0.04, y:cy+r*Math.sin(theta)+(Math.random()-.5)*R*0.04 })
      }
    } else if (shape==='snowflake') {
      const nArms=6, perArm=n/nArms
      for(let arm=0;arm<nArms;arm++){
        const baseA=(arm/nArms)*Math.PI*2, count=arm<n%nArms?Math.ceil(perArm):Math.floor(perArm)
        for(let j=0;j<count;j++){
          const t=(j+1)/(count+1), sp=R*0.05*(1-t)
          pts.push({ x:cx+Math.cos(baseA)*R*t+(Math.random()-.5)*sp*2, y:cy+Math.sin(baseA)*R*t+(Math.random()-.5)*sp*2 })
        }
      }
    } else if (shape==='flower') {
      const nP=6, cN=Math.max(4,Math.floor(n*0.1)), pN=n-cN, perP=pN/nP
      for(let i=0;i<cN;i++){ const a=Math.random()*Math.PI*2,r=Math.random()*R*0.14; pts.push({ x:cx+Math.cos(a)*r, y:cy+Math.sin(a)*r }) }
      for(let p=0;p<nP;p++){
        const baseA=(p/nP)*Math.PI*2, pcx=cx+Math.cos(baseA)*R*0.52, pcy=cy+Math.sin(baseA)*R*0.52
        const count=p<pN%nP?Math.ceil(perP):Math.floor(perP)
        for(let j=0;j<count;j++){ const a=Math.random()*Math.PI*2,r=Math.sqrt(Math.random())*R*0.28; pts.push({ x:pcx+Math.cos(a)*r, y:pcy+Math.sin(a)*r }) }
      }
    } else if (shape==='tree') {
      const trunkN=Math.max(3,Math.floor(n*0.07))
      for(let i=0;i<trunkN;i++) pts.push({ x:cx+(Math.random()-.5)*R*0.1, y:cy+R*0.38+i*(R*0.38/trunkN) })
      const cN=n-trunkN
      for(let i=0;i<cN;i++){
        const lv=Math.sqrt(Math.random()), y=cy-R*0.85+lv*R*1.15, hw=R*0.72*lv
        pts.push({ x:cx+(Math.random()*2-1)*hw, y })
      }
    } else if (shape==='snake') {
      const sp=R*0.09
      for(let i=0;i<n;i++){
        const t=i/n, y=cy+R*1.1*(t-0.5)
        const x=cx+R*0.45*Math.sin(t*Math.PI*3.5)
        pts.push({ x:x+(Math.random()-.5)*sp, y:y+(Math.random()-.5)*sp })
      }
    } else if (shape==='crescent') {
      let att=0
      while(pts.length<n&&att<n*30){
        att++; const a=Math.random()*Math.PI*2,r=Math.sqrt(Math.random())*R
        const px=cx+Math.cos(a)*r, py=cy+Math.sin(a)*r
        const idx=px-(cx+R*0.32), idy=py-cy
        if(idx*idx+idy*idy>(R*0.72)*(R*0.72)) pts.push({ x:px, y:py })
      }
    } else if (shape==='diamond') {
      for(let i=0;i<n;i++){
        const rx=R*0.72, ry=R*0.98
        let x,y
        do{ x=(Math.random()*2-1)*rx; y=(Math.random()*2-1)*ry }while(Math.abs(x)/rx+Math.abs(y)/ry>1)
        pts.push({ x:cx+x, y:cy+y })
      }
    }

    while(pts.length<n) pts.push({ x:cx+(Math.random()-.5)*80, y:cy+(Math.random()-.5)*80 })
    return pts.slice(0,n)
  }

  function activateShape(shapeName) {
    const nl=nodes.get()
    const pts=generateShapePoints(shapeName, nl.length)
    // Nearest-point assignment — each node flows to its closest shape point
    const used=new Set()
    // Sort nodes by distance from center so central nodes get central points
    const sorted=[...nl].map(node=>{ const an=animNodes.get(String(node.id)); return { node, an, dx:an?an.baseX-cssW()/2:0, dy:an?an.baseY-cssH()/2:0 } })
    sorted.forEach(({ node, an })=>{
      if(!an) return
      let best=-1, bestDist=Infinity
      pts.forEach((pt,i)=>{ if(used.has(i)) return; const dx=an.baseX-pt.x,dy=an.baseY-pt.y; const d=dx*dx+dy*dy; if(d<bestDist){bestDist=d;best=i} })
      if(best>=0){ used.add(best); an.shapeTarget={ x:pts[best].x, y:pts[best].y } }
    })
  }

  function deactivateShape() {
    for(const an of animNodes.values()) delete an.shapeTarget
  }

  function rebuildAnimNodes() {
    const nl=nodes.get(), el=edges.get()
    const pos=computeLayout(nl,el)
    animNodes.clear()
    pos.forEach((p,id)=>animNodes.set(id,makeAnimNode(id,p.x,p.y)))
  }

  // Node animation: orbital float + mouse repulsion + optional shape attraction
  function updateAnimNode(an) {
    an.angle+=an.av; an.phase+=0.011
    const ax=Math.cos(an.angle)*an.ar
    const ay=Math.sin(an.angle)*an.ar+Math.cos(an.phase)*5
    // Shape attraction: gently pull baseX/baseY toward shape target
    if(an.shapeTarget){
      an.baseX+=(an.shapeTarget.x-an.baseX)*0.05
      an.baseY+=(an.shapeTarget.y-an.baseY)*0.05
    }
    if(!shiftHeld){
      const dx=mouse.wx-an.x, dy=mouse.wy-an.y
      const dist=Math.sqrt(dx*dx+dy*dy)
      if(dist<mouse.radius&&mouse.wx>-9000){
        const force=(mouse.radius-dist)/mouse.radius
        const angle=Math.atan2(dy,dx)
        an.x-=Math.cos(angle)*force*12
        an.y-=Math.sin(angle)*force*12
        return
      }
    }
    an.x+=(an.baseX+ax-an.x)*0.05
    an.y+=(an.baseY+ay-an.y)*0.05
  }

  function fitAll() {
    const anl=[...animNodes.values()]; if(!anl.length) return
    const xs=anl.map(a=>a.baseX), ys=anl.map(a=>a.baseY)
    const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys)
    const pad=80,cw=cssW(),ch=cssH()
    const sc=Math.min((cw-pad*2)/(maxX-minX||1),(ch-pad*2)/(maxY-minY||1),2)
    cam.ts=Math.max(0.1,Math.min(sc,2))
    cam.tx=cw/2-(minX+maxX)/2*cam.ts
    cam.ty=ch/2-(minY+maxY)/2*cam.ts
    cam.x=cam.tx; cam.y=cam.ty; cam.scale=cam.ts
  }

  const NODE_PALETTE = {
    'Person':{fill:'#2997ff',glow:'rgba(41,151,255,0.8)'},'Skill':{fill:'#30d158',glow:'rgba(48,209,88,0.7)'},
    'Value':{fill:'#ff9f0a',glow:'rgba(255,159,10,0.7)'},'Goal':{fill:'#ff375f',glow:'rgba(255,55,95,0.7)'},
    'Trait':{fill:'#bf5af2',glow:'rgba(191,90,242,0.7)'},'Identity':{fill:'#64d2ff',glow:'rgba(100,210,255,0.7)'},
    'Project':{fill:'#ffd60a',glow:'rgba(255,214,10,0.7)'},'Behavior':{fill:'#ff6961',glow:'rgba(255,105,97,0.7)'},
    'Constraint':{fill:'#ac8e68',glow:'rgba(172,142,104,0.7)'},'Belief':{fill:'#32ade6',glow:'rgba(50,173,230,0.7)'},
  }
  let shapeColorOverride = null
  const dynPalCache = new Map()
  function palFor(type) {
    if (shapeColorOverride) return shapeColorOverride
    if (NODE_PALETTE[type]) return NODE_PALETTE[type]
    if (dynPalCache.has(type)) return dynPalCache.get(type)
    // Hash the label string to a hue, then pick a vivid HSL color
    let h = 0
    for (let i = 0; i < type.length; i++) h = (h * 31 + type.charCodeAt(i)) & 0xffff
    const hue = h % 360
    const fill = `hsl(${hue},80%,62%)`
    const glow = `hsla(${hue},80%,62%,0.75)`
    const pal = { fill, glow }
    dynPalCache.set(type, pal)
    return pal
  }
  function isDark() { return document.documentElement.getAttribute('data-theme')!=='light' }

  function render() {
    if(destroyed) return
    const dpr=window.devicePixelRatio||1
    const W=cssW(),H=cssH()
    ctx.setTransform(dpr,0,0,dpr,0,0)
    ctx.clearRect(0,0,W,H)
    ctx.fillStyle=isDark()?'#0f0f13':'#f5f5f7'
    ctx.fillRect(0,0,W,H)

    cam.x+=(cam.tx-cam.x)*0.1; cam.y+=(cam.ty-cam.y)*0.1; cam.scale+=(cam.ts-cam.scale)*0.1
    ctx.save(); ctx.translate(cam.x,cam.y); ctx.scale(cam.scale,cam.scale)

    // Edges
    for(const eid of edges.getIds()){
      const e=edges.get(eid),a=animNodes.get(String(e.from)),b=animNodes.get(String(e.to)); if(!a||!b) continue
      const isSel=eid===selEdge,isHov=eid===hoveredEdge
      ctx.save(); ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y)
      if(isSel||isHov){ ctx.shadowBlur=10;ctx.shadowColor='rgba(41,151,255,0.6)';ctx.strokeStyle='rgba(96,184,255,0.9)';ctx.lineWidth=2/cam.scale }
      else { const dx=a.x-b.x,dy=a.y-b.y,dist=Math.sqrt(dx*dx+dy*dy),op=Math.max(0.04,0.35-dist/1400); ctx.strokeStyle=`rgba(41,151,255,${op})`;ctx.lineWidth=1/cam.scale }
      ctx.stroke(); ctx.restore()
      if((isSel||isHov)&&e.label){ ctx.font=`${11/cam.scale}px Inter,sans-serif`;ctx.fillStyle='rgba(134,134,139,0.9)';ctx.textAlign='center';ctx.fillText(e.label,(a.x+b.x)/2,(a.y+b.y)/2-7/cam.scale) }
    }

    // Nodes
    for(const [id,an] of animNodes){
      if(id!==draggedNode) updateAnimNode(an)
      const node=nodes.get(id); if(!node) continue
      const isSel=id===selNode,isHov=id===hoveredNode,isHL=searchHL.has(id)
      const type=node.title||'Node',pal=palFor(type)
      const r=(type==='Person'?(isSel?11:9):(isSel?8:6))/cam.scale
      const alpha=isSel?1:isHov?0.95:0.75
      ctx.save()
      ctx.shadowBlur=isSel?28:isHov?18:isHL?22:10
      ctx.shadowColor=isHL?'rgba(255,214,10,0.8)':pal.glow
      ctx.fillStyle=pal.fill+(alpha<1?Math.round(alpha*255).toString(16).padStart(2,'0'):'')
      ctx.strokeStyle=isSel?(isDark()?'#fff':'#1a1a1a'):isHL?'#ffd60a':pal.fill
      ctx.lineWidth=(isSel?2.5:1.5)/cam.scale
      ctx.beginPath(); ctx.arc(an.x,an.y,r,0,Math.PI*2); ctx.fill(); ctx.stroke()
      ctx.restore()
      if(isSel||isHov||isHL){ const label=node._label||node.label||''; const fs=Math.max(9,12/cam.scale); ctx.font=`600 ${fs}px Inter,sans-serif`; ctx.fillStyle=isDark()?'#f5f5f7':'#1a1a1a'; ctx.textAlign='center'; ctx.fillText(label,an.x,an.y-r-6/cam.scale) }
    }
    ctx.restore()
    rafId=requestAnimationFrame(render)
  }

  // Mouse events — shift to select/drag nodes, no-shift = pan + repulsion
  function onMouseMove(e) {
    const rect=canvas.getBoundingClientRect()
    const sx=e.clientX-rect.left, sy=e.clientY-rect.top
    mouse.sx=sx; mouse.sy=sy
    const w=sToW(sx,sy); mouse.wx=w.x; mouse.wy=w.y
    if(draggedNode){ const an=animNodes.get(draggedNode); if(an){an.x=w.x+dragOffX;an.y=w.y+dragOffY;an.baseX=an.x;an.baseY=an.y} didDrag=true; return }
    if(dragging&&!shiftHeld){ cam.tx=camStartX+(sx-dragStartSX); cam.ty=camStartY+(sy-dragStartSY); didDrag=true; return }
    hoveredNode=hitNode(w.x,w.y); hoveredEdge=hoveredNode?null:hitEdge(w.x,w.y)
    canvas.style.cursor=(hoveredNode||hoveredEdge)?'pointer':'grab'
  }
  function onMouseLeave() { mouse.wx=-9999; mouse.wy=-9999; hoveredNode=null; hoveredEdge=null }
  function onMouseDown(e) {
    if(e.button!==0) return
    const rect=canvas.getBoundingClientRect()
    const sx=e.clientX-rect.left, sy=e.clientY-rect.top
    const w=sToW(sx,sy); didDrag=false
    if(e.shiftKey){
      const hn=hitNode(w.x,w.y)
      if(hn){ draggedNode=hn; const an=animNodes.get(hn); dragOffX=an.x-w.x; dragOffY=an.y-w.y; return }
    }
    dragging=true; dragStartSX=sx; dragStartSY=sy; camStartX=cam.tx; camStartY=cam.ty
    canvas.style.cursor='grabbing'
  }
  function onMouseUp(e) {
    if(e.button!==0) return
    const rect=canvas.getBoundingClientRect()
    const w=sToW(e.clientX-rect.left, e.clientY-rect.top)
    if(!didDrag&&e.shiftKey){
      const hn=hitNode(w.x,w.y), he=hn?null:hitEdge(w.x,w.y)
      if(hn){ selNode=hn===selNode?null:hn; selEdge=null }
      else if(he){ selEdge=he===selEdge?null:he; selNode=null }
      else { selNode=null; selEdge=null }
      setSelectedNode(selNode); setSelectedEdge(selEdge)
    }
    draggedNode=null; dragging=false; didDrag=false
    canvas.style.cursor=hoveredNode?'pointer':'grab'
  }
  function onWheel(e) {
    e.preventDefault()
    const rect=canvas.getBoundingClientRect()
    const sx=e.clientX-rect.left, sy=e.clientY-rect.top
    const factor=e.deltaY>0?0.88:1.14
    const ns=Math.max(0.1,Math.min(cam.ts*factor,6))
    const wx=(sx-cam.tx)/cam.ts, wy=(sy-cam.ty)/cam.ts
    cam.tx=sx-wx*ns; cam.ty=sy-wy*ns; cam.ts=ns
    // Brightness flash on zoom
    clearTimeout(zoomTimer)
    canvas.style.filter='brightness(1.35)'
    zoomTimer=setTimeout(()=>{ canvas.style.filter='brightness(1)' },220)
  }
  function onKeyDown(e) { if(e.key==='Shift'){ shiftHeld=true; canvas.style.cursor=hoveredNode?'pointer':'crosshair' } }
  function onKeyUp(e) { if(e.key==='Shift'){ shiftHeld=false; canvas.style.cursor=hoveredNode?'pointer':'grab' } }

  canvas.addEventListener('mousemove',onMouseMove)
  canvas.addEventListener('mouseleave',onMouseLeave)
  canvas.addEventListener('mousedown',onMouseDown)
  canvas.addEventListener('mouseup',onMouseUp)
  canvas.addEventListener('wheel',onWheel,{passive:false})
  window.addEventListener('keydown',onKeyDown)
  window.addEventListener('keyup',onKeyUp)

  async function loadGraph() {
    const resp=await fetch('/api/graph',{headers:authH()}); if(!resp.ok) return
    const data=await resp.json()
    nodes.clear(); edges.clear()
    nodes.add(data.nodes.map(n=>({...n,_label:n.label,label:' '})))
    edges.add(data.edges)
    rebuildAnimNodes()
    setStats({ nodes:nodes.length, edges:edges.length })
    setTimeout(fitAll,50)
  }

  return {
    start() { render(); loadGraph() },
    destroy() {
      destroyed=true; if(rafId) cancelAnimationFrame(rafId); ro.disconnect()
      canvas.removeEventListener('mousemove',onMouseMove)
      canvas.removeEventListener('mouseleave',onMouseLeave)
      canvas.removeEventListener('mousedown',onMouseDown)
      canvas.removeEventListener('mouseup',onMouseUp)
      canvas.removeEventListener('wheel',onWheel)
      window.removeEventListener('keydown',onKeyDown)
      window.removeEventListener('keyup',onKeyUp)
    },
    reload() { loadGraph() },
    getAllNodes() { return nodes.get() },
    getAllEdges() { return edges.get() },
    getNode(id) { return nodes.get(id) },
    getEdge(id) { return edges.get(id) },
    addNode(id,name,label) {
      nodes.add({id,_label:name,label:' ',title:label})
      const cx=cssW()/2, cy=cssH()/2, w=sToW(cx,cy)
      animNodes.set(id,makeAnimNode(id,w.x+(Math.random()-.5)*100,w.y+(Math.random()-.5)*100))
    },
    addEdge(id,from,to,label) { edges.add({id,from,to,label}) },
    deleteNode(id) {
      const connected=edges.get({filter:e=>String(e.from)===id||String(e.to)===id})
      connected.forEach(e=>edges.remove(e.id)); nodes.remove(id); animNodes.delete(id)
      return connected.map(e=>e.id)
    },
    deleteEdge(id) { edges.remove(id) },
    focusNode(id) {
      const an=animNodes.get(id)
      if(an){ cam.ts=1.5; cam.tx=cssW()/2-an.baseX*1.5; cam.ty=cssH()/2-an.baseY*1.5 }
    },
    setHighlight(set) { searchHL=set },
    clearHighlight() { searchHL=new Set() },
    setShape(name) { shapeColorOverride = name ? (SHAPE_COLORS[name]||null) : null; if(name) activateShape(name); else deactivateShape() },
  }
}
