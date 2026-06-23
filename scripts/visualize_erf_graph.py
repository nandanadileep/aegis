"""
Export the Entity-Relation-Fact graph for a person to a fully self-contained
HTML visualization. No external CDN dependencies — everything is inlined.

Usage:
    .venv/bin/python scripts/visualize_erf_graph.py
    .venv/bin/python scripts/visualize_erf_graph.py --person-id erf_demo_test --open

The output HTML can be opened in any browser, even offline.
"""
from __future__ import annotations

import argparse
import json
import os
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from neo4j import GraphDatabase


def load_env() -> None:
    try:
        from dotenv import load_dotenv as _load
        _load()
    except Exception:
        pass


def get_driver() -> Any:
    return GraphDatabase.driver(
        os.getenv("NEO4J_URI"),
        auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")),
        notifications_min_severity="OFF",
    )


def fetch_graph(driver, database: str, person_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch entities and facts for a person."""
    nodes_query = """
    MATCH (e:Entity {person_id: $person_id})
    RETURN e.uuid AS id, e.name AS name_enc, e.type AS type_enc, e.summary AS summary_enc
    """
    edges_query = """
    MATCH (a:Entity {person_id: $person_id})-[f:FACT {person_id: $person_id}]->(b:Entity {person_id: $person_id})
    RETURN a.uuid AS from_id,
           b.uuid AS to_id,
           f.uuid AS id,
           f.fact AS fact_enc,
           f.relation_type AS relation_type,
           f.valid_from AS valid_from,
           f.valid_to AS valid_to,
           f.expired_at AS expired_at,
           f.created_at AS created_at
    """

    with driver.session(database=database) as session:
        node_rows = session.run(nodes_query, person_id=person_id).data()
        edge_rows = session.run(edges_query, person_id=person_id).data()

    # Try to decrypt names if crypto is available
    try:
        from scripts.crypto import dec
    except ImportError:
        from crypto import dec  # type: ignore

    nodes = []
    for row in node_rows:
        name = dec(row.get("name_enc") or "", person_id)
        entity_type = dec(row.get("type_enc") or "", person_id)
        summary = dec(row.get("summary_enc") or "", person_id)
        nodes.append({
            "id": row["id"],
            "label": name,
            "type": entity_type or "Entity",
            "summary": summary,
        })

    edges = []
    for row in edge_rows:
        fact = dec(row.get("fact_enc") or "", person_id)
        expired = bool(row.get("expired_at"))
        edges.append({
            "id": row["id"],
            "from": row["from_id"],
            "to": row["to_id"],
            "label": row.get("relation_type", "FACT"),
            "fact": fact,
            "expired": expired,
            "valid_from": row.get("valid_from"),
            "valid_to": row.get("valid_to"),
            "created_at": row.get("created_at"),
        })

    return {"nodes": nodes, "edges": edges}


def generate_html(data: Dict[str, List[Dict[str, Any]]], person_id: str) -> str:
    """Generate a fully self-contained HTML page with a canvas graph renderer."""
    nodes_json = json.dumps(data["nodes"])
    edges_json = json.dumps(data["edges"])
    palette_json = json.dumps(["#60a5fa", "#34d399", "#f472b6", "#fbbf24", "#a78bfa",
                               "#f87171", "#22d3ee", "#a3e635", "#fb923c", "#e879f9"])

    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ERF Graph — __PERSON_ID__</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0f0f13;
    color: #e2e2e8;
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  header {
    padding: 12px 20px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: rgba(255,255,255,0.02);
    flex-shrink: 0;
  }
  header h1 { font-size: 16px; font-weight: 500; }
  header .stats { font-size: 13px; color: #888; }
  #canvas-wrap {
    flex: 1;
    position: relative;
    cursor: grab;
  }
  #canvas-wrap:active { cursor: grabbing; }
  canvas { display: block; width: 100%; height: 100%; }
  #detail {
    position: absolute;
    bottom: 20px;
    right: 20px;
    width: 340px;
    background: rgba(20,20,26,0.96);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 12px;
    padding: 16px;
    font-size: 13px;
    line-height: 1.5;
    display: none;
    backdrop-filter: blur(8px);
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  }
  #detail h3 { font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; color: #888; }
  #detail .body { color: #e2e2e8; }
  #detail .meta { color: #777; margin-top: 8px; font-size: 12px; }
  .legend {
    position: absolute;
    top: 16px;
    left: 16px;
    background: rgba(20,20,26,0.92);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 10px;
    padding: 12px;
    font-size: 12px;
    max-width: 200px;
  }
  .legend-item { display: flex; align-items: center; gap: 8px; margin: 5px 0; }
  .dot { width: 10px; height: 10px; border-radius: 50%; }
  .hint {
    position: absolute;
    bottom: 16px;
    left: 16px;
    color: #666;
    font-size: 11px;
    pointer-events: none;
  }
</style>
</head>
<body>
<header>
  <h1>Entity-Relation-Fact Graph — __PERSON_ID__</h1>
  <div class="stats">__NODE_COUNT__ nodes · __EDGE_COUNT__ facts</div>
</header>
<div id="canvas-wrap">
  <canvas id="graph"></canvas>
  <div class="legend" id="legend"></div>
  <div id="detail"></div>
  <div class="hint">Drag nodes · Scroll to zoom · Click for details</div>
</div>
<script>
const rawNodes = __NODES_JSON__;
const rawEdges = __EDGES_JSON__;
const palette = __PALETTE_JSON__;

const typeColor = {};
let paletteIdx = 0;
function colorForType(type) {
  if (!typeColor[type]) {
    typeColor[type] = palette[paletteIdx % palette.length];
    paletteIdx++;
  }
  return typeColor[type];
}

const nodes = rawNodes.map(n => ({
  id: n.id,
  label: n.label,
  type: n.type,
  summary: n.summary,
  color: colorForType(n.type),
  x: Math.random() * 800,
  y: Math.random() * 600,
  vx: 0,
  vy: 0,
  radius: 22,
}));

const nodeById = {};
for (const n of nodes) nodeById[n.id] = n;

const edges = rawEdges.map(e => ({
  id: e.id,
  from: nodeById[e.from],
  to: nodeById[e.to],
  label: e.label,
  fact: e.fact,
  expired: e.expired,
  valid_from: e.valid_from,
  valid_to: e.valid_to,
}));

const canvas = document.getElementById("graph");
const ctx = canvas.getContext("2d");
const wrap = document.getElementById("canvas-wrap");

let width, height;
let scale = 1;
let offsetX = 0, offsetY = 0;
let draggingNode = null;
let hoverNode = null;
let lastMouse = { x: 0, y: 0 };

function resize() {
  const rect = wrap.getBoundingClientRect();
  width = rect.width;
  height = rect.height;
  canvas.width = width * window.devicePixelRatio;
  canvas.height = height * window.devicePixelRatio;
  canvas.style.width = width + "px";
  canvas.style.height = height + "px";
  ctx.setTransform(window.devicePixelRatio, 0, 0, window.devicePixelRatio, 0, 0);
}
window.addEventListener("resize", resize);
resize();

function step() {
  const repulsion = 8000;
  const springLength = 160;
  const springK = 0.008;
  const centerK = 0.001;

  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j];
      let dx = a.x - b.x;
      let dy = a.y - b.y;
      let dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const force = repulsion / (dist * dist);
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      a.vx += fx; a.vy += fy;
      b.vx -= fx; b.vy -= fy;
    }
  }

  for (const e of edges) {
    const a = e.from, b = e.to;
    let dx = b.x - a.x;
    let dy = b.y - a.y;
    let dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const force = (dist - springLength) * springK;
    const fx = (dx / dist) * force;
    const fy = (dy / dist) * force;
    a.vx += fx; a.vy += fy;
    b.vx -= fx; b.vy -= fy;
  }

  for (const n of nodes) {
    n.vx += (width / 2 - n.x) * centerK;
    n.vy += (height / 2 - n.y) * centerK;
    n.vx *= 0.85;
    n.vy *= 0.85;
    if (n !== draggingNode) {
      n.x += n.vx;
      n.y += n.vy;
    }
  }
}

function draw() {
  ctx.clearRect(0, 0, width, height);
  ctx.save();
  ctx.translate(offsetX, offsetY);
  ctx.scale(scale, scale);

  for (const e of edges) {
    const a = e.from, b = e.to;
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const nx = dx / dist, ny = dy / dist;

    const startX = a.x + nx * a.radius;
    const startY = a.y + ny * a.radius;
    const endX = b.x - nx * b.radius;
    const endY = b.y - ny * b.radius;

    ctx.beginPath();
    ctx.moveTo(startX, startY);
    ctx.lineTo(endX, endY);
    ctx.strokeStyle = e.expired ? "#444" : "#888";
    ctx.lineWidth = e.expired ? 1 : 2;
    if (e.expired) ctx.setLineDash([6, 5]);
    else ctx.setLineDash([]);
    ctx.stroke();
    ctx.setLineDash([]);

    const headLen = 10;
    const angle = Math.atan2(endY - startY, endX - startX);
    ctx.beginPath();
    ctx.moveTo(endX, endY);
    ctx.lineTo(endX - headLen * Math.cos(angle - Math.PI / 6), endY - headLen * Math.sin(angle - Math.PI / 6));
    ctx.lineTo(endX - headLen * Math.cos(angle + Math.PI / 6), endY - headLen * Math.sin(angle + Math.PI / 6));
    ctx.fillStyle = e.expired ? "#444" : "#888";
    ctx.fill();

    const mx = (startX + endX) / 2;
    const my = (startY + endY) / 2;
    ctx.fillStyle = e.expired ? "#555" : "#bbb";
    ctx.font = "11px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(e.label, mx, my - 7);
  }

  for (const n of nodes) {
    const grad = ctx.createRadialGradient(n.x, n.y, n.radius * 0.5, n.x, n.y, n.radius * 2.2);
    grad.addColorStop(0, n.color);
    grad.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(n.x, n.y, n.radius * 2.2, 0, Math.PI * 2);
    ctx.fill();

    ctx.beginPath();
    ctx.arc(n.x, n.y, n.radius, 0, Math.PI * 2);
    ctx.fillStyle = n.color;
    ctx.fill();
    ctx.strokeStyle = n === hoverNode ? "#fff" : "rgba(255,255,255,0.4)";
    ctx.lineWidth = n === hoverNode ? 3 : 2;
    ctx.stroke();

    ctx.fillStyle = "#fff";
    ctx.font = "bold 12px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(truncate(n.label, 14), n.x, n.y);

    ctx.fillStyle = "#999";
    ctx.font = "10px sans-serif";
    ctx.fillText(n.type, n.x, n.y + n.radius + 13);
  }

  ctx.restore();
}

function truncate(str, max) {
  return str.length > max ? str.slice(0, max - 1) + "…" : str;
}

function toWorld(ex, ey) {
  return { x: (ex - offsetX) / scale, y: (ey - offsetY) / scale };
}

function findNode(x, y) {
  for (let i = nodes.length - 1; i >= 0; i--) {
    const n = nodes[i];
    const dx = x - n.x, dy = y - n.y;
    if (dx * dx + dy * dy <= (n.radius + 6) ** 2) return n;
  }
  return null;
}

function findEdge(x, y) {
  for (const e of edges) {
    const a = e.from, b = e.to;
    const dist = pointLineDist(x, y, a.x, a.y, b.x, b.y);
    if (dist < 10) return e;
  }
  return null;
}

function pointLineDist(px, py, x1, y1, x2, y2) {
  const A = px - x1, B = py - y1;
  const C = x2 - x1, D = y2 - y1;
  const dot = A * C + B * D;
  const len_sq = C * C + D * D;
  let param = len_sq !== 0 ? dot / len_sq : -1;
  let xx, yy;
  if (param < 0) { xx = x1; yy = y1; }
  else if (param > 1) { xx = x2; yy = y2; }
  else { xx = x1 + param * C; yy = y1 + param * D; }
  const dx = px - xx, dy = py - yy;
  return Math.sqrt(dx * dx + dy * dy);
}

function showDetail(html) {
  const d = document.getElementById("detail");
  d.innerHTML = html;
  d.style.display = "block";
}

function hideDetail() {
  document.getElementById("detail").style.display = "none";
}

canvas.addEventListener("mousedown", e => {
  const pos = toWorld(e.offsetX, e.offsetY);
  const n = findNode(pos.x, pos.y);
  if (n) {
    draggingNode = n;
    showDetail(`<h3>Entity</h3><div class="body">${n.label}</div><div class="meta">${n.type}${n.summary ? " · " + n.summary : ""}</div>`);
  } else {
    hideDetail();
  }
});

window.addEventListener("mousemove", e => {
  const rect = canvas.getBoundingClientRect();
  const ex = e.clientX - rect.left;
  const ey = e.clientY - rect.top;
  const pos = toWorld(ex, ey);
  lastMouse = { x: ex, y: ey };

  if (draggingNode) {
    draggingNode.x = pos.x;
    draggingNode.y = pos.y;
    draggingNode.vx = 0;
    draggingNode.vy = 0;
  } else {
    const prevHover = hoverNode;
    hoverNode = findNode(pos.x, pos.y);
    if (hoverNode !== prevHover) {
      canvas.style.cursor = hoverNode ? "pointer" : "grab";
    }
  }
});

window.addEventListener("mouseup", () => {
  draggingNode = null;
});

canvas.addEventListener("wheel", e => {
  e.preventDefault();
  const zoom = e.deltaY > 0 ? 0.9 : 1.1;
  const rect = canvas.getBoundingClientRect();
  const ex = e.clientX - rect.left;
  const ey = e.clientY - rect.top;
  offsetX = ex - (ex - offsetX) * zoom;
  offsetY = ey - (ey - offsetY) * zoom;
  scale *= zoom;
}, { passive: false });

canvas.addEventListener("click", e => {
  const pos = toWorld(e.offsetX, e.offsetY);
  const edge = findEdge(pos.x, pos.y);
  if (edge) {
    const meta = [];
    if (edge.expired) meta.push("EXPIRED");
    if (edge.valid_from) meta.push("from: " + edge.valid_from);
    if (edge.valid_to) meta.push("to: " + edge.valid_to);
    showDetail(`<h3>Fact</h3><div class="body">${edge.fact}</div><div class="meta">${edge.label}${meta.length ? " · " + meta.join(" · ") : ""}</div>`);
  }
});

const legend = document.getElementById("legend");
for (const [type, color] of Object.entries(typeColor)) {
  const item = document.createElement("div");
  item.className = "legend-item";
  item.innerHTML = `<div class="dot" style="background:${color}"></div><span>${type}</span>`;
  legend.appendChild(item);
}

function loop() {
  step();
  draw();
  requestAnimationFrame(loop);
}
loop();
</script>
</body>
</html>
"""
    return (html
            .replace("__PERSON_ID__", person_id)
            .replace("__PERSON_ID__", person_id)
            .replace("__NODES_JSON__", nodes_json)
            .replace("__EDGES_JSON__", edges_json)
            .replace("__PALETTE_JSON__", palette_json)
            .replace("__NODE_COUNT__", str(len(data["nodes"])))
            .replace("__EDGE_COUNT__", str(len(data["edges"]))))



def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize the ERF graph.")
    parser.add_argument("--person-id", default="erf_demo_test", help="Person id to visualize.")
    parser.add_argument("--output", default=None, help="Output HTML path.")
    parser.add_argument("--open", action="store_true", help="Open the HTML in a browser.")
    args = parser.parse_args()

    load_env()
    driver = get_driver()
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    try:
        data = fetch_graph(driver, database, args.person_id)
        html = generate_html(data, args.person_id)

        if args.output:
            out_path = Path(args.output)
        else:
            out_path = Path(f"/tmp/erf_graph_{args.person_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")

        out_path.write_text(html, encoding="utf-8")
        print(f"Wrote visualization to: {out_path}")
        print(f"Nodes: {len(data['nodes'])}, Facts: {len(data['edges'])}")

        if args.open:
            webbrowser.open(f"file://{out_path.resolve()}")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
