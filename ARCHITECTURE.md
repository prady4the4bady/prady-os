# Prady OS v2 System Architecture

**Document Version:** 2.0  
**Last Updated:** 2026  
**Status:** Production (v1.0.0)

## Table of Contents

1. [System Overview](#system-overview)
2. [Service Architecture](#service-architecture)
3. [Data Flow and Orchestration](#data-flow-and-orchestration)
4. [Dependency Chain and Health](#dependency-chain-and-health)
5. [Fallback Strategies](#fallback-strategies)
6. [Security Model](#security-model)
7. [Deployment Model](#deployment-model)
8. [Design Patterns](#design-patterns)

---

## System Overview

Prady OS v2 is a **multi-agent automation system** that translates high-level goals into structured task decomposition, executes those tasks across distributed agents, and produces verifiable artifacts.

### Core Design Principles

- **Modular Services:** Each service has a single responsibility; services communicate via HTTP and Redis.
- **Health-First:** All services expose `/healthz` endpoints; orchestration waits for dependency health before proceeding.
- **Local-First with Fallbacks:** Uses local Ollama when available; falls back to cloud APIs (OpenAI, Anthropic) on failure.
- **Audit Trail:** All activities logged to JSONL files; human approval gates async workflows.
- **Policy-Driven Actions:** Desktop automation gated by configurable security policies.

### Service Inventory

| Service | Port | Language | Role |
|---------|------|----------|------|
| **redis** | 6379 (internal) | Go | State management, message bus |
| **model-gateway** | 11430 | Python | LLM routing, model selection, API gateway |
| **workflow-engine** | 11431 | Python | Task orchestration, approval workflow |
| **screen-agent** | 11433 | Python | Desktop automation, screenshot, vision |
| **lumyn-agent** | 11436 | Python | Primary conversational agent, session management |
| **playwright-runner** | 11432 (host bridge) | Node.js | Browser automation, web task execution |

---

## Service Architecture

### 1. Redis (State & Messaging)

**Responsibility:** Distributed state, session queues, message bus for inter-service coordination.

**Key Interfaces:**
- Connection: `redis://redis:6379` (inside container network)
- Commands used: `LPUSH`, `RPOP` (task queue), `HSET/HGET` (session state)

**Health Check:**
```bash
redis-cli ping
```

**Fallback:** None. Redis unavailability blocks all orchestration.

---

### 2. Model Gateway (LLM Abstraction)

**Responsibility:** Single entry point for all LLM requests; routing logic; credential management.

**Key Capabilities:**
- OpenAI-compatible `/v1/chat/completions` endpoint
- Model registry (`/v1/models`) listing available backends
- Routing policy engine (local-first, cloud fallback)
- Audit logging for all model queries

**Routes:**
```
POST   /v1/chat/completions       → ChatCompletionResponse
POST   /v1/completions            → CompletionResponse
GET    /v1/models                 → [ { id, created, object } ]
GET    /healthz                   → 200 OK | error
```

**Config:** `/app/config/` (mounted read-only from `./ai-core/model-gateway/config/`)

**Routing Modes:**
- `local-first` (default): Try Ollama at `http://host.docker.internal:11434`; fall back to OpenAI.
- `cloud-only`: Skip Ollama; use OpenAI/Anthropic directly.

**Environment:**
```
OLLAMA_BASE_URL=http://host.docker.internal:11434
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=claude-...
LOG_LEVEL=INFO
GATEWAY_ROUTING_MODE=local-first
```

**Fallback Strategy:**
1. Local Ollama (fastest, free)
2. OpenAI API (fallback, requires key)
3. Anthropic API (fallback, requires key)

**Health Check:** `GET /healthz` expects 200 within 5s.

---

### 3. Workflow Engine (Task Orchestration)

**Responsibility:** Decompose high-level goals into subtasks; orchestrate execution; manage human approvals.

**Key Capabilities:**
- Task decomposition using model-gateway
- State machine for task lifecycle (pending → running → approved → completed → failed)
- Approval queue with timeout-based auto-approval or human review
- Redis-backed persistence for multi-step workflows
- Activity logging to JSONL (audit trail)

**Routes:**
```
POST   /task                      → TaskRequest → TaskRecord
GET    /task/{task_id}            → TaskRecord
POST   /task/{task_id}/approve    → { decision: "approve" | "reject" }
GET    /approvals                 → [ ApprovalRecord ]
```

**Orchestration Flow:**
1. User submits goal (e.g., "Search for climate news and summarize")
2. Workflow-engine decomposes into subtasks (search → filter → summarize)
3. Subtasks routed to appropriate services (screen-agent for browser, model-gateway for reasoning)
4. Results collected; approval required if confidence < threshold
5. Approved results returned to user

**Approval Workflow:**
- Tasks with cost or destructive actions require approval
- Approval queue stored in Redis
- Timeout: `APPROVAL_TIMEOUT_SECONDS` (default: 300s)
- Auto-approval if no human decision before timeout

**State Persistence:** Redis + JSONL activity log at `/app/logs/activities.jsonl`

**Environment:**
```
REDIS_URL=redis://redis:6379
MODEL_GATEWAY_URL=http://model-gateway:8000
WORKFLOW_ENGINE_URL=http://workflow-engine:8000
GATEWAY_MODEL=llama3.2:3b
APPROVAL_TIMEOUT_SECONDS=300
ACTIVITY_LOG_DIR=/app/logs
```

**Health Check:** `GET /healthz` expects 200 within 5s; checks Redis connectivity.

---

### 4. Screen Agent (Desktop Automation)

**Responsibility:** Mouse, keyboard, screenshot, and screen vision operations with security gating.

**Key Capabilities:**
- Mouse operations (move, click, drag)
- Keyboard operations (type, key combos)
- Screenshot capture with labels
- Screen vision (describe current state using model-gateway)
- Policy-based action gating (deny dangerous operations)

**Routes:**
```
POST   /actions/mouse-move        → { x, y }
POST   /actions/mouse-click       → { x, y, button: "left"|"right"|"middle" }
POST   /actions/keyboard-type     → { text }
POST   /actions/key-combo         → { keys: ["ctrl", "c"] }
POST   /actions/screenshot        → { label: "after-click" }
GET    /actions/cursor-pos        → { x, y }
POST   /vision/describe-screen    → { prompt, timeout_secs }
GET    /healthz                   → 200 OK | error
```

**Policy Engine:**
- Every action passes through policy check before execution
- Policies defined in YAML; loaded from `/app/config/policy.yaml`
- Actions can be denied, logged, or require approval

**Environment:**
```
SCREEN_AGENT_MODEL_GATEWAY_URL=http://model-gateway:8000
ACTION_POLICY=permissive  # permissive | restrictive | deny-destructive
POLICY_TIMEOUT_SECS=5
VISION_MODEL=vision
VISION_TIMEOUT_SECS=30
ACTIONS_LOG_PATH=logs/actions.jsonl
DISPLAY=:1          # X11 display (Linux)
WAYLAND_DISPLAY=... # Wayland display (if applicable)
XDG_RUNTIME_DIR=... # XDG runtime (for X11 socket)
```

**Fallback Strategy:**
- If DISPLAY unavailable: Log error; reject all actions
- If model-gateway unavailable: Accept actions but skip vision
- If X11/Wayland unavailable: Desktop automation disabled

**Health Check:** `GET /healthz` checks DISPLAY availability; `xdpyinfo` or equivalent.

**Security Boundaries:**
- All actions logged with timestamp and requestor
- Policy denials logged for audit
- No direct shell access (subprocess calls wrapped)

---

### 5. Lumyn Agent (Conversational Layer)

**Responsibility:** Primary user-facing agent; session management; learned strategies.

**Key Capabilities:**
- Multi-turn conversation with context window
- Session persistence (stored in Redis)
- Tools integration (access to model-gateway, workflow-engine, screen-agent)
- Nightly reflection and learning (fine-tuned prompts)
- ReAct loop for reasoning and tool use

**Routes:**
```
POST   /chat                      → ChatRequest → ChatResponse
POST   /execute                   → ExecuteRequest → TaskRecord
POST   /memory/search             → MemorySearchRequest → [ MemoryRecord ]
GET    /learnings                 → [ str ]
GET    /healthz                   → 200 OK | error
```

**Session Lifecycle:**
1. User starts new session
2. Lumyn loads past learnings (from `/app/learnings/learned.jsonl`)
3. ReAct loop generates tool calls (model-gateway, workflow-engine, screen-agent)
4. Tool results incorporated into context
5. Final response returned to user
6. Session stored in Redis

**Learnings/Reflection:**
- Runs nightly via APScheduler
- Analyzes session logs
- Generates new prompts and strategies
- Updates `/app/learnings/learned.jsonl`

**Environment:**
```
SCREEN_AGENT_URL=http://screen-agent:8000
WORKFLOW_ENGINE_URL=http://workflow-engine:8000
MODEL_GATEWAY_URL=http://model-gateway:8000
LUMYN_SESSION_TIMEOUT=3600
LUMYN_LEARNING_SCHEDULE=cron: 0 2 * * *  # 2 AM daily
```

**Health Check:** `GET /healthz` checks all upstream services.

---

### 6. Playwright Runner (Browser Automation)

**Responsibility:** Headless browser control for web task execution.

**Key Capabilities:**
- Page navigation, click, type, screenshot
- JavaScript execution
- Cookie/session management
- Network request inspection

**Routes:**
```
POST   /browser/navigate          → { url }
POST   /browser/click             → { selector }
POST   /browser/type              → { selector, text }
POST   /browser/screenshot        → { label }
POST   /browser/evaluate          → { script }
```

**Host Bridging:** Runs on `host.docker.internal:11432` (Mac/Windows) to access host browser/localhost services.

**Environment:**
- Node.js 20
- Playwright dependencies
- No special env vars required

**Fallback Strategy:**
- If Playwright unavailable: workflow-engine skips browser subtasks
- If host bridge unavailable: Desktop-native fallback via screen-agent

**Health Check:** Connection test to port 11432.

---

## Data Flow and Orchestration

#### 7. Neila — Ouroboros Daemon (Autonomous Background Loop)

**Responsibility:** Persistent background daemon that runs the Ouroboros loop below Prax. Retries failed jobs, triggers scheduled actions, generates digests, consolidates memory, and closes the Prax → Ahnis → Neila loop.

**Key Capabilities:**
- SQLite-backed retry queue with exponential backoff (survives restarts)
- SQLite-backed scheduled actions (survive restarts)
- Digest candidate generation every 10 cycles
- Memory consolidation triggers via Ahnis
- Follow-up candidate generation from Ahnis summaries and unresolved items
- Stalled-task resurfacing (proposals pending >24h)
- Structured audit events with event_type, source, correlation_id, status

**Routes (v1.1.0):**
```
GET    /health                           → HealthResponse
GET    /neila/status                     → NeilaStatusResponse
GET    /neila/metrics                    → MetricsResponse
POST   /neila/pause                      → { status }
POST   /neila/resume                     → { status }
POST   /neila/enqueue                    → EnqueueResponse
GET    /neila/queue                      → [ QueueEntryResponse ]
POST   /neila/schedule                   → ScheduleResponse
GET    /neila/scheduled                  → [ ScheduledEntryResponse ]
POST   /neila/followup                   → { followup_id }
GET    /neila/followups                  → [ FollowupCandidateResponse ]
POST   /neila/followups/{fid}/processed  → { status }
GET    /neila/digests                    → [ DigestCandidateResponse ]
```

**Persistence:** SQLite at `/data/neila.db` (configurable via `NEILA_DB_PATH`). On startup, all pending retries and schedules are restored.

**Environment:**
```
NEILA_TICK_INTERVAL=60        # seconds between cycles
NEILA_DB_PATH=/data/neila.db  # SQLite database path
NEILA_HTTP_TIMEOUT=10.0       # HTTP client timeout
INVENTOR_ENGINE_URL=http://inventor-engine:8022
AUDIT_LOG_URL=http://audit-log:8112
NOTIFICATION_BUS_URL=http://notification-bus:8111
AHNIS_URL=http://ahnis:8028
```

### 8. Ahnis — MemPalace-Aya (Pluggable Semantic Memory)

**Responsibility:** Semantic memory and retrieval with pluggable embedding architecture. Provides write, search, summarize, consolidate, and delete operations across six categories: conversation, task, skill, project, summary, failure_lesson.

**Key Capabilities:**
- Pluggable embedding providers:
  1. **LocalHashProvider** — deterministic hash-based (always available, 64-dim)
  2. **SentenceTransformerProvider** — learned semantic embeddings when sentence-transformers installed
  3. **QdrantProvider** — optional Qdrant vector storage
- Provider selection via `AHNIS_EMBEDDING_MODE` env var (auto | local-hash | sentence-transformer | qdrant)
- In-memory store with consolidation (trims to 1000 when >2000 per category)
- Structured search with scoring: exact match → token overlap → fuzzy → fallback
- Deterministic local embedding as fallback always preserved
- Provider info, dimension, and backend capability exposed in status/metrics

**Routes (v1.1.0):**
```
GET    /health                           → HealthResponse
GET    /ahnis/status                     → AhnisStatusResponse
GET    /ahnis/embeddings/provider        → EmbeddingInfo
GET    /ahnis/metrics                    → MetricsResponse
POST   /memory/write                     → WriteResponse
POST   /memory/search                    → SearchResponse
POST   /memory/summarize                 → SummarizeResponse
POST   /memory/consolidate               → ConsolidateResponse
DELETE /memory/{entry_id}                → DeleteResponse
GET    /memory/skills                    → [ dict ]
GET    /memory/projects                  → [ dict ]
POST   /memory/summarize_legacy          → { summary, count } (backward-compat)
POST   /memory/consolidate_legacy        → { status, entries_before/after } (backward-compat)
```

**Environment:**
```
AHNIS_EMBEDDING_MODE=auto          # auto | local-hash | sentence-transformer | qdrant
AHNIS_ST_MODEL=all-MiniLM-L6-v2    # sentence-transformers model name
QDRANT_HOST=""                     # Qdrant host (empty = disabled)
QDRANT_PORT=6333
AUDIT_LOG_URL=http://audit-log:8112
```

### 9. Prax → Ahnis → Neila Loop

The memory loop closes the feedback cycle between task execution (Prax), memory storage (Ahnis), and background orchestration (Neila):

```
Prax executes task
  ↓
Prax writes episodic memory to Ahnis at task boundaries
  ↓
Neila reads Ahnis summaries and unresolved items every 5 cycles
  ↓
Neila generates follow-up candidates from Ahnis context
  ↓
Neila creates digest candidates from Inventor Engine every 10 cycles
  ↓
Neila triggers memory consolidation via Ahnis every cycle
  ↓
Follow-up and digest candidates available via /neila/followups, /neila/digests
```

This loop is fully local-first. No cloud APIs required.

## High-Level Flow

```
User Goal (e.g., "Find and summarize today's climate news")
    ↓
Lumyn Agent (chat endpoint)
    ↓ Calls /v1/chat/completions on model-gateway
    ↓
Model Gateway (selects best LLM)
    ↓ Routes to local Ollama or cloud API
    ↓
Lumyn generates decomposed subtasks (search → filter → summarize)
    ↓
Workflow Engine (POST /task)
    ↓ Decomposes into executable steps
    ↓
Step Routing:
  - Search query → screen-agent (browser) or playwright-runner
  - Article fetch → playwright-runner
  - Text summarization → model-gateway (/v1/chat/completions)
  - User approval (if confidence < threshold) → approval queue
    ↓
Results aggregated
    ↓
Lumyn formats final response
    ↓ Returns to user
```

### State Persistence

- **Session State:** Redis (key: `session:{session_id}`)
- **Approval Queue:** Redis (key: `approvals:pending`)
- **Activity Trail:** JSONL files
  - `ai-core/model-gateway/logs/queries.jsonl` (all LLM queries)
  - `orchestration/workflow-engine/logs/activities.jsonl` (all tasks)
  - `automation/screen-agent/logs/actions.jsonl` (all desktop actions)
  - `agents/lumyn/logs/sessions.jsonl` (all conversations)

### Audit Trail

Every significant operation is logged to JSONL with:
- Timestamp (ISO 8601)
- Operation type
- Requestor / session ID
- Input / output
- Result (success/failure/denied)

Example:
```json
{
  "timestamp": "2025-01-15T14:30:45.123Z",
  "event": "task_decomposed",
  "session_id": "sess_123",
  "goal": "Find climate news",
  "subtasks": [
    { "id": "st_1", "action": "navigate_browser", "url": "https://news.hn" },
    { "id": "st_2", "action": "summarize", "text": "..." }
  ]
}
```

---

## Dependency Chain and Health

### Startup Order

```
1. redis              (no dependencies)
   ↓ Health: redis-cli ping
   
2. model-gateway      (depends: redis, optional Ollama)
   ↓ Health: GET /healthz
   
3. workflow-engine    (depends: redis, model-gateway)
   ↓ Health: GET /healthz
   
4. screen-agent       (depends: model-gateway, X11/Wayland)
   ↓ Health: GET /healthz
   
5. lumyn-agent       (depends: model-gateway, workflow-engine, screen-agent)
   ↓ Health: GET /healthz
   
6. playwright-runner  (optional, depends: host network bridge)
   ↓ Health: Port 11432 reachable
```

### Health Checks

All services implement `/healthz` with:
- 200 OK if healthy
- 503 Service Unavailable if dependent service unreachable
- 5s timeout; fail-fast design

**Redis Health:**
```bash
redis-cli -u redis://redis:6379 ping
```

**Model Gateway Health:**
```bash
curl http://model-gateway:8000/healthz
```

**Workflow Engine Health:**
```bash
curl http://workflow-engine:8000/healthz
```

**Screen Agent Health:**
```bash
curl http://screen-agent:8000/healthz
```

**Lumyn Agent Health:**
```bash
curl http://lumyn-agent:8000/healthz
```

---

## Fallback Strategies

### Scenario 1: Ollama Unavailable

**Symptom:** model-gateway logs "Ollama connection failed; trying OpenAI"

**Behavior:**
- Falls back to OpenAI API
- Requires `OPENAI_API_KEY` set
- Slightly higher latency and cost
- Continues operations

**Manual Recovery:**
```bash
# Start local Ollama
ollama serve &

# Or, explicitly set cloud-only mode
export GATEWAY_ROUTING_MODE=cloud-only
```

### Scenario 2: OpenAI API Unavailable

**Symptom:** model-gateway logs "OpenAI API unreachable"

**Behavior:**
- Falls back to Anthropic (if key available)
- If both cloud APIs fail, returns 503 to caller
- Workflow-engine retries with exponential backoff (3 attempts)

**Manual Recovery:**
```bash
# Verify API keys set
env | grep -E "OPENAI_API_KEY|ANTHROPIC_API_KEY"

# Manual retry after key update
curl -X POST http://workflow-engine:8000/task/retry \
  -H "Content-Type: application/json" \
  -d '{"task_id": "task_123"}'
```

### Scenario 3: Redis Unavailable

**Symptom:** workflow-engine logs "Redis connection failed"

**Behavior:**
- All services fail to initialize
- Orchestration completely blocked
- No state persistence

**Manual Recovery:**
```bash
docker-compose up redis
# Wait for redis to be healthy
docker-compose logs redis
# Restart all dependent services
docker-compose restart model-gateway workflow-engine
```

### Scenario 4: Screen Agent / DISPLAY Unavailable

**Symptom:** lumyn-agent logs "Screen agent unhealthy"

**Behavior:**
- Desktop automation tasks fail
- Browser automation via playwright-runner continues
- Workflow-engine skips visual navigation tasks

**Manual Recovery:**
```bash
# Start X server (if running on headless system)
Xvfb :1 -screen 0 1920x1080x24 &
export DISPLAY=:1

# Or, via VNC
vncserver :1 -geometry 1920x1080
export DISPLAY=:1

# Restart screen-agent
docker-compose restart screen-agent
```

### Scenario 5: Playwright Runner Unavailable

**Symptom:** workflow-engine logs "Playwright runner unreachable"

**Behavior:**
- Browser tasks fail
- Workflow-engine retries with screen-agent fallback (if available)
- Non-browser tasks continue

**Manual Recovery:**
```bash
# Verify host bridge
ping host.docker.internal  # or your host IP

# Restart playwright-runner
docker-compose restart playwright-runner

# Or, skip playwright entirely
export PLAYWRIGHT_RUNNER_URL=http://disabled:11432
```

---

## Security Model

### Trust Boundaries

```
                    ┌─────────────────────────────┐
                    │   Untrusted User Input      │
                    │  (goals, queries, commands) │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   Lumyn Agent              │ ← ReAct loop validates
                    │  (prompt injection checks)  │
                    └──────────────┬──────────────┘
                                   │
       ┌───────────────────────────┼───────────────────────────┐
       │                           │                           │
       ▼                           ▼                           ▼
┌────────────────┐        ┌────────────────┐        ┌────────────────┐
│Model Gateway   │        │Workflow Engine │        │Screen Agent    │
│(API routing)   │        │(orchestration) │        │(policy gating) │
│ - Auth tokens  │        │ - Approval     │        │ - Action check │
│ - Rate limits  │        │   workflow     │        │ - DISPLAY      │
│ - Audit log    │        │ - Audit log    │        │ - Audit log    │
└────────────────┘        └────────────────┘        └────────────────┘
```

### Key Security Controls

1. **API Gateway (model-gateway)**
   - All LLM requests routed through single gateway
   - API keys never exposed to agents
   - Rate limiting per model
   - Request audit logging

2. **Approval Workflow (workflow-engine)**
   - Destructive actions (file delete, send email) require human approval
   - Timeout-based auto-approval (configurable)
   - Approval decision logged

3. **Policy Gating (screen-agent)**
   - Every action checked against policy YAML
   - Policies: `permissive`, `restrictive`, `deny-destructive`
   - Failed action logged and rejected

4. **Audit Trail**
   - All operations logged to JSONL with requestor, timestamp, result
   - Centralized log collection possible via sidecar
   - No PII logged (URLs, filenames redacted)

### Secrets Management

- **API Keys:** Stored in `.env`, injected as environment variables
- **No Keys in Docker:** Keys never baked into images
- **Redis Authentication:** Not required for internal network (design assumes trusted internal network)
- **Suggested Improvements:** Use vault-agent sidecar or AWS Secrets Manager in production

---

## Deployment Model

### Local Development

```bash
# Setup
make dev-up         # Starts all services locally (docker-compose)
make logs          # Tail logs
make test-e2e      # Run E2E tests

# Verify health
curl http://localhost:11430/healthz  # model-gateway
curl http://localhost:11431/healthz  # workflow-engine
curl http://localhost:11433/healthz  # screen-agent
curl http://localhost:11436/healthz  # lumyn-agent
```

### Docker Compose (Production-like)

- Single `docker-compose.yml` with all 6 services
- Optional `docker-compose.dev.yml` overrides (debug logging, volume mounts)
- Health checks on all services
- Automatic restart on failure (`unless-stopped`)
- Shared network `kryos-net`

**Startup:**
```bash
docker-compose up -d
docker-compose ps
```

**Monitoring:**
```bash
docker-compose logs -f workflow-engine
docker-compose exec redis redis-cli DBSIZE
```

### Cloud Deployment (Future)

- Kubernetes manifests (Helm charts) for orchestration layer
- Managed PostgreSQL for persistent state (replacing Redis)
- API Gateway (Kong, AWS API Gateway) for rate limiting
- Secrets Manager (Vault, AWS Secrets Manager) for credentials
- Observability stack (Prometheus, Jaeger) for tracing

---

## Design Patterns

### 1. Service-Oriented Architecture (SOA)

Each service is independently deployable, scalable, and maintainable.

- **Example:** model-gateway can be scaled horizontally; workflow-engine remains single-instance.

### 2. Strangler Pattern (Phased Rollout)

Services can be replaced incrementally without affecting others.

- **Example:** Replace Python workflow-engine with Rust implementation; maintain same HTTP interface.

### 3. Circuit Breaker (Fallback Routing)

Model gateway implements circuit breaker for cloud APIs.

- **State:** Closed (normal) → Open (failing) → Half-Open (testing)
- **Action:** If OpenAI fails 5× consecutively, try Anthropic.

### 4. ReAct Loop (Reasoning + Acting)

Lumyn uses ReAct pattern for multi-step reasoning with tool use.

```
Thought: "I need to search for climate news"
Action: "navigate_browser(url=https://news.hn)"
Observation: "Browser loaded 10 articles"
Thought: "I should filter for climate-related articles"
Action: "filter_articles(query='climate')"
...
Final Answer: "Here are the top climate articles..."
```

### 5. Saga Pattern (Distributed Transactions)

Workflow-engine uses saga pattern for multi-step workflows.

```
Step 1: Decompose goal ✓
Step 2: Schedule subtasks ✓
Step 3: Execute with approval ✓ (or rollback)
Step 4: Aggregate results ✓
```

If Step 3 fails, workflow pauses; human decides retry or abort.

### 6. Event-Driven (Redis Pub/Sub)

Services emit events to Redis; other services subscribe.

- **Example:** workflow-engine emits `task:completed` event; lumyn subscribes and continues conversation.

---

## Troubleshooting Guide

### Service Won't Start

1. Check logs: `docker-compose logs <service>`
2. Verify dependencies healthy: `docker-compose ps`
3. Check port conflicts: `lsof -i :<port>`
4. Restart dependencies: `docker-compose restart redis`

### High Latency / Slow Responses

1. Check redis memory: `redis-cli INFO memory`
2. Check model-gateway routing: `GATEWAY_ROUTING_MODE=local-first` or `cloud-only`?
3. Check network: `docker network inspect kryos-net`
4. Monitor logs: `make logs | grep -i error`

### API Errors (500, 503)

1. Check upstream service health: `curl http://<service>:8000/healthz`
2. Check Redis connectivity: `docker-compose exec redis redis-cli ping`
3. Check environment variables: `docker-compose config | grep <service>`
4. Review logs: `docker-compose logs <service> --tail 100`

### Lost Sessions / Data

1. Redis not persisted: Sessions stored in-memory only; restarting redis clears state
2. **Solution:** Implement Redis persistence (`save`, `appendonly`) or use PostgreSQL in production

---

## Future Roadmap

1. **Kubernetes Migration:** Replace docker-compose with Helm charts
2. **Observability:** Add Prometheus metrics, Jaeger tracing, ELK logging
3. **Scale:** Horizontal scaling for model-gateway, lumyn-agent
4. **Persistence:** PostgreSQL backend for session and approval state
5. **Analytics:** Learnings database; model performance tracking

---

**Document Owner:** Prady OS Team  
**Last Reviewed:** 2026
