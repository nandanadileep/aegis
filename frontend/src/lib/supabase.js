import { createClient } from '@supabase/supabase-js'

const API = import.meta.env.VITE_API_URL ?? ''

let _sb = null

export async function getSupabase() {
  if (_sb) return _sb
  const cfg = await fetch(`${API}/api/config`).then(r => r.json())
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
