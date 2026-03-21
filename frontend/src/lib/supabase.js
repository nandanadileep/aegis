import { createClient } from '@supabase/supabase-js'

const API = import.meta.env.VITE_API_URL ?? ''

let _sb = null
const CFG_KEY = 'identiti_cfg'

export async function getSupabase() {
  if (_sb) return _sb
  // Use build-time env vars if available (fastest — no network call)
  const builtinUrl = import.meta.env.VITE_SUPABASE_URL
  const builtinKey = import.meta.env.VITE_SUPABASE_ANON_KEY
  if (builtinUrl && builtinKey) {
    _sb = createClient(builtinUrl, builtinKey)
    return _sb
  }
  // Fall back to cached config, then fetch from backend
  let cfg = null
  try { cfg = JSON.parse(localStorage.getItem(CFG_KEY)) } catch {}
  if (!cfg?.supabase_url) {
    cfg = await fetch(`${API}/api/config`).then(r => r.json())
    try { localStorage.setItem(CFG_KEY, JSON.stringify(cfg)) } catch {}
  }
  _sb = createClient(cfg.supabase_url, cfg.supabase_anon_key)
  return _sb
}

export function authHeaders(session) {
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${session.access_token}`,
  }
  const key = localStorage.getItem('byok_key')
  const model = localStorage.getItem('byok_model')
  if (key && model) {
    headers['X-LLM-Key'] = key
    headers['X-LLM-Model'] = model
  }
  return headers
}
