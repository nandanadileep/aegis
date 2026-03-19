import { useEffect, useRef, useState } from 'react'
import { getSupabase } from '../lib/supabase'
import ThemeToggle from '../components/ThemeToggle'

// ── Shared button styles ──
const S = {
  btn: { display:'inline-flex',alignItems:'center',gap:5,padding:'7px 14px',borderRadius:40,fontSize:13,fontWeight:600,cursor:'pointer',border:'1px solid var(--border-strong)',background:'var(--bg)',color:'var(--text)',fontFamily:'Inter,sans-serif',transition:'all .15s',whiteSpace:'nowrap',letterSpacing:'-0.01em' },
  btnPrimary: { background:'var(--text)',border:'none',color:'var(--bg)' },
}

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
    if (!resp.ok) { alert('Failed'); return }
    const data = await resp.json()
    graphRef.current?.addNode(String(data.id), name, label)
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
    if (!confirm(`Delete "${n?._label||selectedNode}"?`)) return
    const removed = g?.deleteNode(selectedNode) || []
    setStats(s => ({ ...s, nodes: s.nodes-1, edges: s.edges - removed.length }))
    setPending(p => ({ ...p, deletedNodes:[...p.deletedNodes,selectedNode], deletedEdges:[...p.deletedEdges,...removed] }))
    setSelectedNode(null)
  }

  function doDeleteEdge() {
    if (!selectedEdge) return
    const e = graphRef.current?.getEdge(selectedEdge)
    if (!confirm(`Delete "${e?.label||selectedEdge}"?`)) return
    graphRef.current?.deleteEdge(selectedEdge)
    setStats(s => ({ ...s, edges: s.edges-1 }))
    setPending(p => ({ ...p, deletedEdges:[...p.deletedEdges,selectedEdge] }))
    setSelectedEdge(null)
  }

  async function doCommit() {
    const resp = await fetch('/api/commit', { method:'POST', headers:authH(), body:JSON.stringify(pendingRef.current) })
    if (!resp.ok) { alert('Commit failed'); return }
    setPending({ nodes:{}, edges:{}, deletedNodes:[], deletedEdges:[] })
    graphRef.current?.reload(authH)
    setModal(null)
  }

  function doReset() {
    if (!confirm('Discard all pending changes?')) return
    setPending({ nodes:{}, edges:{}, deletedNodes:[], deletedEdges:[] })
    graphRef.current?.reload(authH)
  }

  async function downloadWallet() {
    const resp = await fetch('/api/wallet', { headers:authH() })
    const blob = await resp.blob()
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download='twin_card.md'; a.click()
    URL.revokeObjectURL(a.href)
  }

  const pendingCount = Object.keys(pending.nodes).length + Object.keys(pending.edges).length + pending.deletedNodes.length + pending.deletedEdges.length
  const selectedNodeData = selectedNode && graphRef.current?.getNode(selectedNode)
  const selectedEdgeData = selectedEdge && graphRef.current?.getEdge(selectedEdge)

  const TYPE_COLORS = { 'Person':'#2997ff','Skill':'#30d158','Value':'#ff9f0a','Goal':'#ff375f','Trait':'#bf5af2','Identity':'#64d2ff','Project':'#ffd60a','Behavior':'#ff6961','Constraint':'#ac8e68','Belief':'#32ade6' }

  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100vh', background:'var(--bg)', overflow:'hidden' }}>
      {/* Header */}
      <header style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'0 24px', height:60, borderBottom:'1px solid var(--border)', flexShrink:0, background:'var(--bg)', gap:12, zIndex:50 }}>
        <span style={{ fontSize:15, fontWeight:800, letterSpacing:'-0.03em', flexShrink:0 }}>Aegis</span>
        <nav style={{ display:'flex', gap:4, flexShrink:0 }}>
          <a href="/chat" style={{ padding:'6px 14px', borderRadius:80, fontSize:13, fontWeight:500, color:'var(--text-2)', textDecoration:'none', border:'1px solid transparent' }}>Chat</a>
          <a href="/memory" style={{ padding:'6px 14px', borderRadius:80, fontSize:13, fontWeight:500, color:'var(--text)', textDecoration:'none', border:'1px solid var(--border-strong)', background:'var(--surface)' }}>Graph</a>
        </nav>
        <div style={{ flex:1, maxWidth:280 }}>
          <input value={searchQ} onChange={e=>setSearchQ(e.target.value)} onKeyDown={e=>{ if(e.key==='Enter') runSearch(); if(e.key==='Escape'){setSearchQ('');setSearchResults(null);graphRef.current?.clearHighlight()} }}
            placeholder="Search nodes & relationships…"
            style={{ width:'100%', background:'var(--surface)', border:'1px solid var(--border)', borderRadius:80, color:'var(--text)', fontFamily:'Inter,sans-serif', fontSize:13, padding:'7px 16px', outline:'none' }} />
        </div>
        <div style={{ display:'flex', gap:6, flexShrink:0, alignItems:'center' }}>
          <span style={{ padding:'4px 12px', borderRadius:80, fontSize:11, fontWeight:700, background: pendingCount>0?'rgba(0,0,238,0.1)':'var(--surface)', border:`1px solid ${pendingCount>0?'rgba(0,0,238,0.3)':'var(--border)'}`, color: pendingCount>0?'#0000ee':'var(--text-2)' }}>{pendingCount} pending</span>
          <button style={S.btn} onClick={downloadWallet}>⬇ Twin Card</button>
          <ThemeToggle />
          <button style={S.btn} onClick={signOut}>Sign out</button>
          <button style={{ ...S.btn, opacity: pendingCount===0?.35:1 }} disabled={pendingCount===0} onClick={doReset}>Reset</button>
          <button style={{ ...S.btn, background:'#f0fdf4', borderColor:'#86efac', color:'#16a34a', opacity:pendingCount===0?.3:1 }} disabled={pendingCount===0} onClick={()=>setModal('commit')}>Commit</button>
        </div>
      </header>

      <div style={{ display:'flex', flex:1, overflow:'hidden' }}>
        {/* Canvas */}
        <div style={{ flex:1, position:'relative', background:'var(--surface-2)', overflow:'hidden', borderRight:'1px solid var(--border)' }}>
          <canvas ref={canvasRef} style={{ width:'100%', height:'100%', display:'block', cursor:'grab' }} />
        </div>

        {/* Sidebar */}
        <div style={{ width:280, flexShrink:0, background:'var(--bg)', borderLeft:'1px solid var(--border)', display:'flex', flexDirection:'column', overflowY:'auto' }}>
          <Section label="Graph">
            <StatRow k="Nodes" v={stats.nodes} />
            <StatRow k="Relationships" v={stats.edges} />
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
              {selectedNodeData.title && <DR k="Type" v={<span style={{ color:TYPE_COLORS[selectedNodeData.title]||'var(--text-2)' }}>{selectedNodeData.title}</span>} />}
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
    </div>
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

  // DataSet
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
  const mouse = { sx:-9999, sy:-9999, wx:-9999, wy:-9999 }
  let dragging=false, dragStartSX=0, dragStartSY=0, camStartX=0, camStartY=0
  let draggedNode=null, dragOffX=0, dragOffY=0, didDrag=false
  let hoveredNode=null, hoveredEdge=null
  let selNode=null, selEdge=null
  let searchHL=new Set()
  let shiftHeld=false

  function resize() { const r=canvas.parentElement.getBoundingClientRect(); canvas.width=r.width; canvas.height=r.height }
  const ro = new ResizeObserver(resize)
  ro.observe(canvas.parentElement)
  resize()

  function authH() { return { 'Content-Type':'application/json','Authorization':`Bearer ${sessionRef.current?.access_token}` } }

  function sToW(sx,sy) { return { x:(sx-cam.x)/cam.scale, y:(sy-cam.y)/cam.scale } }
  function hitNode(wx,wy) { const r=10/cam.scale; for(const [id,an] of animNodes){ const dx=an.x-wx,dy=an.y-wy; if(dx*dx+dy*dy<r*r) return id } return null }
  function hitEdge(wx,wy) {
    const th=7/cam.scale
    for(const eid of edges.getIds()){ const e=edges.get(eid); const a=animNodes.get(String(e.from)),b=animNodes.get(String(e.to)); if(!a||!b) continue; const dx=b.x-a.x,dy=b.y-a.y,l2=dx*dx+dy*dy; if(!l2) continue; const t=Math.max(0,Math.min(1,((wx-a.x)*dx+(wy-a.y)*dy)/l2)); const px=a.x+t*dx-wx,py=a.y+t*dy-wy; if(px*px+py*py<th*th) return eid }
    return null
  }

  function computeLayout(nl,el) {
    const W=canvas.width||800,H=canvas.height||600
    const pos=new Map()
    nl.forEach((n,i)=>{ const a=(i/nl.length)*Math.PI*2; pos.set(String(n.id),{ x:W/2+Math.cos(a)*220,y:H/2+Math.sin(a)*220 }) })
    for(let iter=0;iter<120;iter++){
      const forces=new Map(); nl.forEach(n=>forces.set(String(n.id),{x:0,y:0}))
      nl.forEach((a,i)=>{ nl.slice(i+1).forEach(b=>{ const pa=pos.get(String(a.id)),pb=pos.get(String(b.id)); let dx=pb.x-pa.x,dy=pb.y-pa.y; const d=Math.sqrt(dx*dx+dy*dy)||1; const f=-6000/(d*d); const fa=forces.get(String(a.id)),fb=forces.get(String(b.id)); fa.x+=dx/d*f; fa.y+=dy/d*f; fb.x-=dx/d*f; fb.y-=dy/d*f }) })
      el.forEach(e=>{ const pa=pos.get(String(e.from)),pb=pos.get(String(e.to)); if(!pa||!pb) return; const dx=pb.x-pa.x,dy=pb.y-pa.y; const d=Math.sqrt(dx*dx+dy*dy)||1; const f=(d-120)*0.05; const fa=forces.get(String(e.from)),fb=forces.get(String(e.to)); if(fa){fa.x+=dx/d*f;fa.y+=dy/d*f} if(fb){fb.x-=dx/d*f;fb.y-=dy/d*f} })
      nl.forEach(n=>{ const p=pos.get(String(n.id)),f=forces.get(String(n.id)); if(p&&f){p.x+=f.x*.35;p.y+=f.y*.35} })
    }
    return pos
  }

  function makeAnimNode(id,x,y) { return { x,y,baseX:x,baseY:y,angle:Math.random()*Math.PI*2,av:(Math.random()-.5)*.015,phase:Math.random()*Math.PI*2,ar:2.5+Math.random()*1.5 } }
  function rebuildAnimNodes() { const nl=nodes.get(),el=edges.get(); const pos=computeLayout(nl,el); nl.forEach(n=>{ const p=pos.get(String(n.id)); animNodes.set(String(n.id),makeAnimNode(String(n.id),p?.x||0,p?.y||0)) }) }
  function updateAnimNode(an) { const spd=0.08,mag=0.012; an.angle+=an.av; an.phase+=.01; const tx=an.baseX+Math.cos(an.angle)*an.ar,ty=an.baseY+Math.sin(an.angle)*an.ar; an.x+=(tx-an.x)*spd; an.y+=(ty-an.y)*spd }

  function fitAll() {
    const anl=[...animNodes.values()]; if(!anl.length) return
    let mx=Infinity,mn=-Infinity,my=Infinity,mny=-Infinity
    anl.forEach(a=>{ mx=Math.min(mx,a.x);mn=Math.max(mn,a.x);my=Math.min(my,a.y);mny=Math.max(mny,a.y) })
    const pad=80,cw=canvas.width||800,ch=canvas.height||600
    const sc=Math.min((cw-pad*2)/(mn-mx||1),(ch-pad*2)/(mny-my||1),.8)
    cam.ts=Math.max(.15,Math.min(sc,2)); cam.tx=cw/2-(mx+mn)/2*cam.ts; cam.ty=ch/2-(my+mny)/2*cam.ts
    cam.x=cam.tx; cam.y=cam.ty; cam.scale=cam.ts
  }

  const NODE_PALETTE = {
    'Person':{fill:'#2997ff',glow:'rgba(41,151,255,0.8)'},'Skill':{fill:'#30d158',glow:'rgba(48,209,88,0.7)'},
    'Value':{fill:'#ff9f0a',glow:'rgba(255,159,10,0.7)'},'Goal':{fill:'#ff375f',glow:'rgba(255,55,95,0.7)'},
    'Trait':{fill:'#bf5af2',glow:'rgba(191,90,242,0.7)'},'Identity':{fill:'#64d2ff',glow:'rgba(100,210,255,0.7)'},
    'Project':{fill:'#ffd60a',glow:'rgba(255,214,10,0.7)'},'Behavior':{fill:'#ff6961',glow:'rgba(255,105,97,0.7)'},
    'Constraint':{fill:'#ac8e68',glow:'rgba(172,142,104,0.7)'},'Belief':{fill:'#32ade6',glow:'rgba(50,173,230,0.7)'},
  }
  const DEF_PAL = { fill:'#2997ff',glow:'rgba(41,151,255,0.75)' }

  function isDark() { return document.documentElement.getAttribute('data-theme')!=='light' }

  function render() {
    if(destroyed) return
    ctx.clearRect(0,0,canvas.width,canvas.height)
    // Background
    ctx.fillStyle = isDark() ? '#0f0f13' : '#f5f5f7'
    ctx.fillRect(0,0,canvas.width,canvas.height)

    cam.x+=(cam.tx-cam.x)*.1; cam.y+=(cam.ty-cam.y)*.1; cam.scale+=(cam.ts-cam.scale)*.1
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
      const type=node.title||'Node',pal=NODE_PALETTE[type]||DEF_PAL
      const r=(type==='Person'?(isSel?11:9):(isSel?8:6))/cam.scale
      const alpha=isSel?1:isHov?.95:.75
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

  // Mouse events
  function onMouseMove(e) {
    const rect=canvas.getBoundingClientRect(); const sx=e.clientX-rect.left,sy=e.clientY-rect.top; mouse.sx=sx;mouse.sy=sy; const w=sToW(sx,sy); mouse.wx=w.x;mouse.wy=w.y
    if(draggedNode){ const an=animNodes.get(draggedNode); if(an){an.x=w.x+dragOffX;an.y=w.y+dragOffY;an.baseX=an.x;an.baseY=an.y} didDrag=true; return }
    if(dragging&&!shiftHeld){ cam.tx=camStartX+(mouse.sx-dragStartSX);cam.ty=camStartY+(mouse.sy-dragStartSY);didDrag=true; return }
    hoveredNode=hitNode(w.x,w.y); hoveredEdge=hoveredNode?null:hitEdge(w.x,w.y)
    canvas.style.cursor=(hoveredNode||hoveredEdge)?'pointer':'grab'
  }
  function onMouseLeave() { mouse.wx=-9999;mouse.wy=-9999;hoveredNode=null;hoveredEdge=null }
  function onMouseDown(e) {
    const w=sToW(e.clientX-canvas.getBoundingClientRect().left,e.clientY-canvas.getBoundingClientRect().top)
    const hn=hitNode(w.x,w.y)
    if(hn&&shiftHeld){ draggedNode=hn; const an=animNodes.get(hn); dragOffX=an.x-w.x;dragOffY=an.y-w.y;didDrag=false; return }
    dragging=true; dragStartSX=mouse.sx;dragStartSY=mouse.sy;camStartX=cam.tx;camStartY=cam.ty;didDrag=false
  }
  function onMouseUp() {
    if(draggedNode){ draggedNode=null } else if(!didDrag){
      const hn=hitNode(mouse.wx,mouse.wy),he=hn?null:hitEdge(mouse.wx,mouse.wy)
      selNode=hn||null; selEdge=he||null
      setSelectedNode(selNode); setSelectedEdge(selEdge)
    }
    dragging=false; didDrag=false
  }
  function onWheel(e) { e.preventDefault(); const f=e.deltaY<0?1.1:.91; const sx=e.clientX-canvas.getBoundingClientRect().left,sy=e.clientY-canvas.getBoundingClientRect().top; cam.ts=Math.max(.07,Math.min(cam.ts*f,5)); cam.tx=sx-(sx-cam.tx)*(cam.ts/cam.scale); cam.ty=sy-(sy-cam.ty)*(cam.ts/cam.scale) }
  function onKeyDown(e) { if(e.key==='Shift'){shiftHeld=true;canvas.style.cursor=hoveredNode?'pointer':'crosshair'} }
  function onKeyUp(e) { if(e.key==='Shift'){shiftHeld=false;canvas.style.cursor=hoveredNode?'pointer':'grab'} }

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
    reload(getHeaders) { loadGraph() },
    getAllNodes() { return nodes.get() },
    getAllEdges() { return edges.get() },
    getNode(id) { return nodes.get(id) },
    getEdge(id) { return edges.get(id) },
    addNode(id,name,label) { nodes.add({id,_label:name,label:' ',title:label}); const cx=canvas.width/2,cy=canvas.height/2,w=sToW(cx,cy); animNodes.set(id,makeAnimNode(id,w.x+(Math.random()-.5)*100,w.y+(Math.random()-.5)*100)) },
    addEdge(id,from,to,label) { edges.add({id,from,to,label}) },
    deleteNode(id) { const connected=edges.get({filter:e=>String(e.from)===id||String(e.to)===id}); connected.forEach(e=>{edges.remove(e.id)}); nodes.remove(id); animNodes.delete(id); return connected.map(e=>e.id) },
    deleteEdge(id) { edges.remove(id) },
    focusNode(id) { const an=animNodes.get(id); if(an){ cam.ts=1.5; cam.tx=canvas.width/2-an.baseX*1.5; cam.ty=canvas.height/2-an.baseY*1.5 } },
    setHighlight(set) { searchHL=set },
    clearHighlight() { searchHL=new Set() },
  }
}
