# Aegis — remember me, but softly

A tiny memory-forward chat that picks up where you left off. Groq for brains, Neo4j for heart, Flask + vanilla HTML for the shell.

## Run it
```bash
python3 app.py
# then open http://localhost:5000
```

## Env you need
- `GROQ_API_KEY`
- `GROQ_MODEL` (defaults to `llama-3.3-70b-versatile`)
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`
- optional: `PERSON_ID` (defaults to `nandana_dileep`)

## How it feels
- Chat naturally; the assistant quietly uses your graph memory.
- Type `/exit` or just close the tab to save the convo back into memories.
- `GET /health` returns a simple ok for checks.

## Where things live
- `app.py` – Flask API + Groq calls
- `index.html` – minimal dark UI
- `scripts/memory_pipeline.py` – extraction + staging + Neo4j writes
