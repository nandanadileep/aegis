# Identiti

Your memory lives here. Chat with an AI that knows who you are — and builds your knowledge graph as you talk.

## Architecture

```mermaid
flowchart TD
    User["User (Browser)"]

    subgraph Frontend ["Frontend — React + Vite"]
        Login["Login\n/login"]
        Onboarding["Onboarding\n/onboarding"]
        Chat["Chat\n/chat"]
        Graph["Graph\n/memory"]
    end

    subgraph Backend ["Backend — Flask (port 3000)"]
        Auth["Auth Middleware\nSupabase JWT"]

        subgraph ChatFlow ["Chat Flow"]
            ChatAPI["/chat"]
            EntityExtract["Entity Extraction\nLLM"]
        end

        subgraph OnboardFlow ["Onboard Flow"]
            OnboardChat["/api/onboard-chat\nLLM"]
            ImportAPI["/api/import\nLLM → parse memory"]
        end

        subgraph GraphAPI ["Graph API"]
            GetGraph["/api/graph"]
            CreateNode["/api/graph/node\nLLM → normalize label"]
            DeleteNode["/api/graph/node DELETE"]
        end

        WalletAPI["/api/wallet\nTwin Card export"]
        SaveAPI["/save\nTranscript → pipeline"]
    end

    subgraph AI ["LLM — Groq llama-3.3-70b"]
        LLM["litellm.completion"]
    end

    subgraph Storage ["Storage"]
        Neo4j[("Neo4j\nKnowledge Graph")]
        Supabase[("Supabase\nAuth")]
        Redis[("Redis\nConversation History")]
    end

    ExternalAI["ChatGPT / Claude\n(memory export)"]

    User -->|"Google OAuth"| Supabase
    Supabase -->|JWT| Auth

    User --> Login --> Onboarding
    Onboarding -->|"onboard-chat"| OnboardChat
    Onboarding -->|"paste memory export"| ImportAPI
    ExternalAI -->|"JSON profile"| ImportAPI

    User --> Chat --> ChatAPI
    ChatAPI -->|"read memory context"| Neo4j
    ChatAPI -->|"conversation history"| Redis
    ChatAPI --> LLM
    ChatAPI --> EntityExtract --> LLM
    EntityExtract -->|"MERGE nodes"| Neo4j

    User --> Graph --> GetGraph --> Neo4j
    Graph --> CreateNode --> LLM
    CreateNode -->|"MERGE node"| Neo4j
    Graph --> DeleteNode --> Neo4j

    OnboardChat --> LLM
    OnboardChat -->|"profile → import"| ImportAPI
    ImportAPI --> LLM
    ImportAPI -->|"MERGE person + nodes"| Neo4j

    ChatAPI --> SaveAPI --> Neo4j
    WalletAPI --> Neo4j
```

## Stack

| Layer | Tech |
|-------|------|
| Frontend | React + Vite, canvas graph renderer |
| Backend | Flask (Python) |
| Auth | Supabase (Google OAuth) |
| LLM | Groq — llama-3.3-70b via litellm |
| Graph DB | Neo4j |
| Cache | Redis (conversation history) |

## Where AI is called

| Endpoint | Purpose |
|----------|---------|
| `/chat` | Generate replies using memory context |
| `/chat` (post-reply) | Extract entities from conversation → graph nodes |
| `/api/onboard-chat` | Onboarding conversation → profile JSON |
| `/api/import` | Parse memory export → structured profile |
| `/api/graph/node` | Normalize user-typed labels (spelling correction) |
| `/api/wallet` | (reads graph, no LLM) |

## Run it

```bash
python3 app.py
# open http://localhost:3000
```

## Env vars

```
GROQ_API_KEY
LLM_MODEL          # default: groq/llama-3.3-70b-versatile
NEO4J_URI
NEO4J_USER
NEO4J_PASSWORD
NEO4J_DATABASE
SUPABASE_URL
SUPABASE_JWT_SECRET
REDIS_URL           # optional
```
