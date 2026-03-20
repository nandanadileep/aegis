const SHAPE_COLORS = {
  octopus:  {fill:'#7c5c9e',glow:'rgba(124,92,158,0.5)'},
  jellyfish:{fill:'#a8607e',glow:'rgba(168,96,126,0.5)'},
  fish:     {fill:'#4a8fa8',glow:'rgba(74,143,168,0.5)'},
  whale:    {fill:'#3a6b8a',glow:'rgba(58,107,138,0.5)'},
  starfish: {fill:'#b07840',glow:'rgba(176,120,64,0.5)'},
  butterfly:{fill:'#8c5a9e',glow:'rgba(140,90,158,0.5)'},
  heart:    {fill:'#a04a52',glow:'rgba(160,74,82,0.5)'},
  bird:     {fill:'#5a8faa',glow:'rgba(90,143,170,0.5)'},
  spiral:   {fill:'#3a8c84',glow:'rgba(58,140,132,0.5)'},
  snowflake:{fill:'#6a9aa0',glow:'rgba(106,154,160,0.5)'},
  flower:   {fill:'#a05878',glow:'rgba(160,88,120,0.5)'},
  tree:     {fill:'#4a8464',glow:'rgba(74,132,100,0.5)'},
  snake:    {fill:'#567a40',glow:'rgba(86,122,64,0.5)'},
  crescent: {fill:'#9a8840',glow:'rgba(154,136,64,0.5)'},
  diamond:  {fill:'#3a9a8e',glow:'rgba(58,154,142,0.5)'},
  ring:     {fill:'#5a7eaa',glow:'rgba(90,126,170,0.5)'},
  galaxy:   {fill:'#7a4a9e',glow:'rgba(122,74,158,0.5)'},
  dna:      {fill:'#3a9e7a',glow:'rgba(58,158,122,0.5)'},
  cross:    {fill:'#9e3a4a',glow:'rgba(158,58,74,0.5)'},
  infinity: {fill:'#5a3a9e',glow:'rgba(90,58,158,0.5)'},
  crown:    {fill:'#9e8a3a',glow:'rgba(158,138,58,0.5)'},
  mountain: {fill:'#5a7a5a',glow:'rgba(90,122,90,0.5)'},
  wave:     {fill:'#3a7a9e',glow:'rgba(58,122,158,0.5)'},
}

export default function initGraph(canvas, sessionRef, setStats, setPending, setSelectedNode, setSelectedEdge, setGraphLoading) {
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
  const DRAG_THRESHOLD=4 // px — below this a mousedown+up is treated as a click
  let hoveredNode=null, hoveredEdge=null
  let selNode=null, selEdge=null
  let searchHL=new Set()
  let mouseDownSX=0, mouseDownSY=0
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
    const r=18/Math.pow(cam.scale,0.5)
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
    } else if (shape==='ring') {
      const innerR=R*0.45, outerR=R*1.0
      let att=0
      while(pts.length<n&&att<n*30){ att++; const a=Math.random()*Math.PI*2,r=innerR+Math.random()*(outerR-innerR); pts.push({ x:cx+Math.cos(a)*r, y:cy+Math.sin(a)*r }) }
    } else if (shape==='galaxy') {
      // Core
      const coreN=Math.floor(n*0.15)
      for(let i=0;i<coreN;i++){ const a=Math.random()*Math.PI*2,r=Math.random()*R*0.15; pts.push({ x:cx+Math.cos(a)*r, y:cy+Math.sin(a)*r*0.6 }) }
      // Two arms
      const armN=n-coreN, half=Math.floor(armN/2)
      const turns=2.5, tMax=turns*Math.PI*2
      for(let arm=0;arm<2;arm++){
        const count=arm===0?half:armN-half, offset=arm*Math.PI
        for(let i=0;i<count;i++){
          const theta=(i/count)*tMax, r=(theta/tMax)*R*1.1, spread=R*0.06*(theta/tMax)
          pts.push({ x:cx+r*Math.cos(theta+offset)+(Math.random()-.5)*spread*2, y:cy+r*Math.sin(theta+offset)*0.7+(Math.random()-.5)*spread })
        }
      }
    } else if (shape==='dna') {
      const strand=Math.floor(n/2)
      for(let i=0;i<n;i++){
        const t=i/n, y=cy-R*1.1+t*R*2.2, phase=t*Math.PI*5, side=i<strand?1:-1
        pts.push({ x:cx+side*R*0.42*Math.cos(phase)+(Math.random()-.5)*R*0.06, y })
      }
    } else if (shape==='cross') {
      const armW=R*0.28, armL=R*1.1
      for(let i=0;i<n;i++){
        if(Math.random()<0.5) pts.push({ x:cx+(Math.random()*2-1)*armL, y:cy+(Math.random()*2-1)*armW })
        else pts.push({ x:cx+(Math.random()*2-1)*armW, y:cy+(Math.random()*2-1)*armL })
      }
    } else if (shape==='infinity') {
      for(let i=0;i<n;i++){
        const t=(i/n)*Math.PI*2, denom=1+Math.sin(t)*Math.sin(t)
        const x=R*1.05*Math.cos(t)/denom, y=R*0.52*Math.sin(t)*Math.cos(t)/denom
        const j=R*0.04*(Math.random()-.5)
        pts.push({ x:cx+x+j, y:cy+y+j })
      }
    } else if (shape==='crown') {
      const baseN=Math.floor(n*0.35)
      for(let i=0;i<baseN;i++) pts.push({ x:cx+(Math.random()*2-1)*R, y:cy+R*0.3+(Math.random()-.5)*R*0.12 })
      const toothN=n-baseN, nTeeth=5
      for(let t=0;t<nTeeth;t++){
        const tx=cx+(t/(nTeeth-1)-0.5)*2*R*0.95, count=Math.ceil(toothN/nTeeth)
        for(let j=0;j<count&&pts.length<n;j++) pts.push({ x:tx+(Math.random()-.5)*R*0.12, y:cy+R*0.3-(j/count)*R*0.8 })
      }
    } else if (shape==='mountain') {
      for(let i=0;i<n;i++){
        const x=cx+(Math.random()*2-1)*R*1.2, nx=(x-(cx-R*1.2))/(R*2.4)
        const peak1=Math.exp(-Math.pow((nx-0.35)*5,2)), peak2=Math.exp(-Math.pow((nx-0.68)*5,2))*0.75
        const h=(peak1+peak2)*R*1.1, y=cy+R*0.4-Math.random()*h
        pts.push({ x, y })
      }
    } else if (shape==='wave') {
      for(let i=0;i<n;i++){
        const x=cx+(Math.random()*2-1)*R*1.2, nx=(x-cx)/R
        const y=cy+R*0.55*Math.sin(nx*Math.PI*2)+(Math.random()-.5)*R*0.08
        pts.push({ x, y })
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
  function updateAnimNode(an, id) {
    an.angle+=an.av; an.phase+=0.011
    const ax=Math.cos(an.angle)*an.ar
    const ay=Math.sin(an.angle)*an.ar+Math.cos(an.phase)*5
    // Shape attraction: gently pull baseX/baseY toward shape target
    if(an.shapeTarget){
      an.baseX+=(an.shapeTarget.x-an.baseX)*0.05
      an.baseY+=(an.shapeTarget.y-an.baseY)*0.05
    }
    // Freeze hovered node completely so it can be clicked
    if(id === hoveredNode) return
    if(id !== draggedNode){
      const dx=mouse.wx-an.x, dy=mouse.wy-an.y
      const dist=Math.sqrt(dx*dx+dy*dy)
      // Safe zone: nodes within 24px of cursor are never repelled (prevents flee-before-hover)
      const safeR=24/cam.scale
      if(dist>safeR && dist<mouse.radius && mouse.wx>-9000){
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
    'Person':{fill:'#4a7fa8',glow:'rgba(74,127,168,0.5)'},'Skill':{fill:'#4a8c62',glow:'rgba(74,140,98,0.5)'},
    'Value':{fill:'#a07840',glow:'rgba(160,120,64,0.5)'},'Goal':{fill:'#9a4a52',glow:'rgba(154,74,82,0.5)'},
    'Trait':{fill:'#7c5a9e',glow:'rgba(124,90,158,0.5)'},'Identity':{fill:'#4a8a9e',glow:'rgba(74,138,158,0.5)'},
    'Project':{fill:'#9a8840',glow:'rgba(154,136,64,0.5)'},'Behavior':{fill:'#a05858',glow:'rgba(160,88,88,0.5)'},
    'Constraint':{fill:'#7a6a52',glow:'rgba(122,106,82,0.5)'},'Belief':{fill:'#3a7a9e',glow:'rgba(58,122,158,0.5)'},
  }
  let showLabels = false
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
      if(id!==draggedNode) updateAnimNode(an, id)
      const node=nodes.get(id); if(!node) continue
      const isSel=id===selNode,isHov=id===hoveredNode,isHL=searchHL.has(id)
      const type=node.title||'Node',pal=palFor(type)
      const r=(type==='Person'?(isSel?11:9):(isSel?8:6))/Math.pow(cam.scale,0.5)
      const alpha=isSel?1:isHov?0.95:0.75
      ctx.save()
      ctx.shadowBlur=isSel?28:isHov?18:isHL?22:10
      ctx.shadowColor=isHL?'rgba(255,214,10,0.8)':pal.glow
      ctx.fillStyle=pal.fill+(alpha<1?Math.round(alpha*255).toString(16).padStart(2,'0'):'')
      ctx.strokeStyle=isSel?(isDark()?'#fff':'#1a1a1a'):isHL?'#ffd60a':pal.fill
      ctx.lineWidth=(isSel?2.5:1.5)/cam.scale
      ctx.beginPath(); ctx.arc(an.x,an.y,r,0,Math.PI*2); ctx.fill(); ctx.stroke()
      ctx.restore()
      if(isSel||isHov||isHL||showLabels){ const label=node._label||node.label||''; const fs=Math.max(9,12/cam.scale); ctx.font=`600 ${fs}px Inter,sans-serif`; ctx.fillStyle=isDark()?'#f5f5f7':'#1a1a1a'; ctx.textAlign='center'; ctx.fillText(label,an.x,an.y-r-6/cam.scale) }
    }
    ctx.restore()
    rafId=requestAnimationFrame(render)
  }

  // Mouse events — click to select, drag node to move, drag canvas to pan
  function onMouseMove(e) {
    const rect=canvas.getBoundingClientRect()
    const sx=e.clientX-rect.left, sy=e.clientY-rect.top
    mouse.sx=sx; mouse.sy=sy
    const w=sToW(sx,sy); mouse.wx=w.x; mouse.wy=w.y
    if(draggedNode){
      const dx=sx-mouseDownSX, dy=sy-mouseDownSY
      if(!didDrag && Math.sqrt(dx*dx+dy*dy)<DRAG_THRESHOLD) return
      const an=animNodes.get(draggedNode); if(an){an.x=w.x+dragOffX;an.y=w.y+dragOffY;an.baseX=an.x;an.baseY=an.y}
      didDrag=true; return
    }
    if(dragging){ cam.tx=camStartX+(sx-dragStartSX); cam.ty=camStartY+(sy-dragStartSY); didDrag=true; return }
    hoveredNode=hitNode(w.x,w.y); hoveredEdge=hoveredNode?null:hitEdge(w.x,w.y)
    canvas.style.cursor=(hoveredNode||hoveredEdge)?'pointer':'grab'
  }
  function onMouseLeave() { mouse.wx=-9999; mouse.wy=-9999; hoveredNode=null; hoveredEdge=null }
  function onMouseDown(e) {
    e.preventDefault() // prevent browser text-selection when shift is held
    if(e.button!==0) return
    const rect=canvas.getBoundingClientRect()
    const sx=e.clientX-rect.left, sy=e.clientY-rect.top
    const w=sToW(sx,sy)
    mouseDownSX=sx; mouseDownSY=sy; didDrag=false
    const hn=hitNode(w.x,w.y)
    if(hn){ draggedNode=hn; const an=animNodes.get(hn); dragOffX=an.x-w.x; dragOffY=an.y-w.y; canvas.style.cursor='grabbing'; return }
    dragging=true; dragStartSX=sx; dragStartSY=sy; camStartX=cam.tx; camStartY=cam.ty
    canvas.style.cursor='grabbing'
  }
  function onMouseUp(e) {
    if(e.button!==0) return
    const rect=canvas.getBoundingClientRect()
    const w=sToW(e.clientX-rect.left, e.clientY-rect.top)
    if(!didDrag){
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
  function onKeyDown(e) { if(e.key==='Escape'){ selNode=null; selEdge=null; setSelectedNode(null); setSelectedEdge(null) } }

  canvas.addEventListener('mousemove',onMouseMove)
  canvas.addEventListener('mouseleave',onMouseLeave)
  canvas.addEventListener('mousedown',onMouseDown)
  canvas.addEventListener('mouseup',onMouseUp)
  canvas.addEventListener('wheel',onWheel,{passive:false})
  window.addEventListener('keydown',onKeyDown)

  async function loadGraph() {
    setGraphLoading?.(true)
    try {
      const resp=await fetch('/api/graph',{headers:authH()}); if(!resp.ok) return
      const data=await resp.json()
      nodes.clear(); edges.clear()
      nodes.add(data.nodes.map(n=>({...n,_label:n.label,label:' '})))
      edges.add(data.edges)
      rebuildAnimNodes()
      setStats({ nodes:nodes.length, edges:edges.length })
      setTimeout(fitAll,50)
    } finally {
      setGraphLoading?.(false)
    }
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
    renameNode(id, newName) { nodes.update({ id, _label: newName }) },
    focusNode(id) {
      const an=animNodes.get(id)
      if(an){ cam.ts=1.5; cam.tx=cssW()/2-an.baseX*1.5; cam.ty=cssH()/2-an.baseY*1.5 }
    },
    setHighlight(set) { searchHL=set },
    clearHighlight() { searchHL=new Set() },
    setShape(name) { shapeColorOverride = name ? (SHAPE_COLORS[name]||null) : null; if(name) activateShape(name); else deactivateShape() },
    setShowLabels(v) { showLabels = v },
  }
}
