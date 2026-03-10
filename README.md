# Aegis — remember me, but softly

A tiny memory-forward chat that picks up where you left off. Groq for brains, Neo4j for heart, Flask + vanilla HTML for the shell.

## Run it
```bash
python3 app.py
# then open http://localhost:5000
```

## Env you need
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (defaults to `gpt-4o-mini`)
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`
- `REDIS_URL` (Redis list store for `conversation_history:<person_id>`)
  - For Upstash, use the TCP URL from "Connect to your database", typically `rediss://default:<password>@<host>:6379`
- optional: `PERSON_ID` (defaults to `nandana_dileep`)

## How it feels
- Chat naturally; the assistant quietly uses your graph memory.
- Type `/exit` or just close the tab to save the convo back into memories.
- `GET /health` returns a simple ok for checks.
- Optional multi-user routing: use `?person_id=<id>` in the URL (or send `person_id`/`X-Person-Id` on API calls).

## Where things live
- `app.py` – Flask API + Groq calls
- `index.html` – minimal dark UI
- `scripts/memory_pipeline.py` – extraction + Redis staging (`staging:<person_id>`) + Neo4j writes

## Performance notes
- `run_pipeline()` accepts optional `redis_client` and `neo4j_driver` parameters to avoid connection overhead on frequent calls
