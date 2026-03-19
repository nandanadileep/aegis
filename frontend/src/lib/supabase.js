import { createClient } from '@supabase/supabase-js'

let _sb = null

export async function getSupabase() {
  if (_sb) return _sb
  const cfg = await fetch('/api/config').then(r => r.json())
  _sb = createClient(cfg.supabase_url, cfg.supabase_anon_key)
  return _sb
}

export function authHeaders(session) {
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${session.access_token}`,
  }
}
