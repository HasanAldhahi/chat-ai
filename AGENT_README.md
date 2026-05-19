# Chat AI — Goose Branch

This branch extends Chat AI with an **agentic layer** that runs Goose-powered agents inside a container runtime and streams their activity back to the browser in real time.

---

## Architecture

```
Browser
  └─ front (React 19 + Vite, :8080)
       └─ back (Express proxy, :8081)
            ├─ OpenAI API  ← standard chat
            └─ agentic (FastAPI broker, :8001)
                 └─ container / HPC runtime  ← agent jobs
```

Agent requests are routed by `isAgentModelRequestBody()` in the backend. The agentic service maps model IDs → runtimes via `agent_registry.py` and streams events via `sse_hub.py`.

---

## Prerequisites

| Tool | Version |
|------|---------|
| Node.js | 18 + |
| npm | 9 + |
| Python | 3.11 + |
| Docker + Compose | 24 + (optional, for containerised run) |

---

## Secrets

Create the secrets directory and config files (not committed):

```
secrets/
  front.json    # frontend runtime config
  back.json     # backend API keys / proxy config
```

Minimal `secrets/back.json`:

```json
{
  "OPENAI_API_KEY": "sk-..."
}
```

Minimal `secrets/front.json`:

```json
{
  "VITE_BACK_URL": "http://localhost:8081"
}
```

---

## Running locally (three terminals)

### 1. Frontend

```bash
cd front
npm install
npm run dev
# → http://localhost:8080
```

### 2. Backend

```bash
cd back
npm install
npm run start
# → http://localhost:8081
```

### 3. Agentic service

```bash
cd agentic
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Development (mock Slurm + mock Vault — no HPC cluster needed)
AGENTIC_SLURM_MOCK_MODE=true AGENTIC_VAULT_MOCK_MODE=true \
  uvicorn app.main:app --port 8001 --reload
# → http://localhost:8001
```

---

## Running with Docker Compose

```bash
# Build and start all three services
docker compose up --build

# Start detached
docker compose up -d --build

# Tear down
docker compose down
```

Services run with `network_mode: host` so ports 8080, 8081, and 8001 are exposed directly on the host.

---

## Environment variables (agentic)

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENTIC_ENVIRONMENT` | `development` | Runtime environment label |
| `AGENTIC_HOST` | `0.0.0.0` | Bind address |
| `AGENTIC_PORT` | `8001` | Listen port |
| `AGENTIC_CORS_ALLOW_ORIGINS` | `http://localhost:3000,http://localhost:5173` | Allowed CORS origins |
| `AGENTIC_SLURM_MOCK_MODE` | `true` | Use synthetic job IDs (dev); set `false` on HPC |
| `AGENTIC_SLURM_BASE_URL` | `http://localhost:6820` | Real Slurm REST endpoint (production) |
| `AGENTIC_VAULT_MOCK_MODE` | `true` | Skip Vault (dev); set `false` when Vault is wired |
| `AGENTIC_VAULT_BASE_URL` | `http://localhost:8200` | HashiCorp Vault address (production) |

---

## Key source files

| File | Role |
|------|------|
| `agentic/app/agent_chat.py` | Agent request entry point |
| `agentic/app/agent_orchestrator.py` | Maps requests to job runners |
| `agentic/app/services/agent_registry.py` | Model ID → runtime mapping |
| `agentic/app/services/sse_hub.py` | Server-Sent Events streaming |
| `front/src/constants/chatAiAgentModels.js` | Agent model IDs (must match registry) |
| `front/src/components/Conversation/MessageAssistant/GooseTerminalRenderer.jsx` | Renders Goose agent output |
| `front/src/components/Conversation/MessageAssistant/AgentActivityFeed.jsx` | Live activity / action feed |

> **Invariant**: model IDs in `chatAiAgentModels.js` must match `agent_registry.py`.  
> Enforced by `agentic/tests/test_agent_registry.py`.

---

## Testing

```bash
# Frontend unit tests
cd front && npm test

# Backend tests
cd back && node --test ./test/*.mjs

# Agentic tests
cd agentic && source .venv/bin/activate
pytest -q

# SSE-specific tests
pytest tests/test_sse.py -v
```

---

## Admin / monitoring

A live session monitor endpoint is available during development:

```
GET http://localhost:8001/api/admin/status
```

Agent sessions idle for more than 60 seconds are auto-terminated by the broker.
