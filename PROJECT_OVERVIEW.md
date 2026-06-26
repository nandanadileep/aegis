Aegis — Project Overview
========================

Aegis is a personalized AI memory layer. It listens to conversations,
extracts what matters, and stores it in a private, per-user knowledge graph.
Later, when the user chats again, Aegis retrieves the relevant memories so
the AI can respond like an old friend.


What it is made of
------------------

app.py
  The main Flask server. Handles chat, OpenAI-compatible chat completions,
  memory context, wallet export, user onboarding, and health checks.

scripts/graph_memory.py
  The core memory engine. Builds and searches a temporal knowledge graph
  using Neo4j.

scripts/user_summary.py
  Turns a user's facts into a short natural-language summary.

scripts/visualize_erf_graph.py
  Draws an HTML canvas view of the memory graph. No external CDN.

scripts/demo_graph_memory.py
  A smoke-test/demo that runs the pipeline with mock or real LLMs.

scripts/chat_with_memory.py
  A simple command-line chat client that loads memory before talking.

mcp_server.py
  An MCP (Model Context Protocol) server so external agents can read/write
  memory.

scripts/crypto.py
  Encrypts and decrypts all user data with per-user keys.

External services
  - Neo4j      : stores the Entity-Relation-Fact graph and communities.
  - Redis      : stores recent conversation history and cached summaries.
  - LiteLLM    : talks to LLM providers (Groq, OpenAI, etc.).


Key features
------------

1. Entity extraction
   From each message, the system pulls out people, places, organizations,
   skills, projects, goals, technologies, and other concepts.

2. Fact extraction
   It links entities with facts:
     (Nandana)-[USES]->(Neo4j)
     fact: "Nandana uses Neo4j for the AI memory app."

3. Entity resolution
   If the same entity is mentioned again with a slightly different name,
   it is merged into one node instead of creating duplicates.

4. Temporal awareness
   Every fact gets a valid time window:
   - "started two weeks ago" -> valid_from = two weeks ago
   - "used to work at Google" -> valid_to = now (past tense)
   - "no longer drinks coffee" -> valid_from = now (negation)
   Untimed facts are valid from the moment they are recorded.

5. Contradiction detection
   When a new fact conflicts with an old one, the old fact is marked as
   expired and its valid_to is set to the new fact's valid_from.
   Uses fast rules first (negation words like "no longer", "stopped", "quit")
   and falls back to an LLM when unsure.

6. Retrieval (vector + BM25 + BFS + reranker)
   Given a user question, the system:
   - scores facts by embedding similarity and token overlap (BM25),
   - walks the graph outward from the top entities (BFS),
   - merges the two lists and reranks them.
   Reranking supports:
   - RRF (Reciprocal Rank Fusion, default)
   - MMR (Maximal Marginal Relevance for diversity)
   - optional cross-encoder (requires sentence-transformers)

7. Community detection
   After each write, the graph is re-clustered into semantic communities.
   - Connected components group tightly linked entities.
   - Large groups are split by embedding similarity.
   - Each community gets a name, a one-line summary, and top facts.
   Communities are stored as :Community nodes for easy browsing.

8. User summary
   Periodically, top retrieved facts are condensed into a short paragraph
   that describes the user. This paragraph is cached in Redis.

9. Wallet / profile export
   /api/wallet returns a self-contained HTML memory profile that can be
   viewed or carried to another system.

10. MCP server
    External agents can call get_memory(person_id, query) and
    add_memory(transcript, person_id).

11. Per-user encryption
    Every fact, entity name, summary, and community text is encrypted with
    a key derived from the user's person_id.


Typical flow
------------

User sends a message
        |
        v
Extract entities and facts
        |
        v
Resolve duplicates, detect contradictions, mark old facts expired
        |
        v
Store entities and facts in Neo4j with temporal fields
        |
        v
Re-detect communities and summarize them
        |
        v
When replying, retrieve relevant memories and build the answer


Environment variables
---------------------

NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE
REDIS_URL
LLM_MODEL, LLM_FAST, LLM_FALLBACK_LIST
EMBEDDING_MODEL (optional; if set, embeddings are stored and used)
DAILY_MSG_LIMIT


Notes
-----

- Embeddings are optional. Without them, retrieval falls back to BM25 and
  graph expansion.
- Community summarization uses one batched LLM call per pipeline run to
  keep latency reasonable.
- Cross-encoder reranking is optional; RRF works with no extra dependencies.
