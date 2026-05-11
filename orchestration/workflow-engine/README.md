# Kryos Orchestration Engine

Phase 2 of the Kryos AI stack. Receives high-level goals, decomposes them into a DAG of sub-tasks via the Phase 1 model-gateway, dispatches sub-tasks to typed agents, enforces approval policies, and writes a structured activity log.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  POST /tasks  (FastAPI)                  │
└──────────────────────────┬──────────────────────────────┘
                           │ TaskRequest
                    ┌──────▼──────┐
                    │  Conductor  │ ─── POST /v1/chat/completions ──▶ model-gateway (11430)
                    └──────┬──────┘
              DAG           │  subtasks
         ┌─────────────────┼─────────────────────┐
         ▼                 ▼                     ▼
   BrowserAgent       ShellAgent    FileAgent / ResearchAgent
         │                 │
         └────────────────▶│◀────── Redis Streams (kryos:stream:agent:*)
                           │
                    activity.jsonl
```

### Components

| File | Responsibility |
|---|---|
| `app/conductor.py` | Goal → DAG → parallel dispatch → summarise |
| `app/dag.py` | Dependency graph, cycle detection, ready-to-run |
| `app/bus.py` | Redis Streams wrapper (XADD / XREADGROUP / XACK) |
| `app/approvals.py` | Approval store with `asyncio.Event` gating |
| `app/activity_log.py` | Append-only JSONL activity log |
| `app/agents/` | Browser / Shell / File / Research agent implementations |
| `app/main.py` | FastAPI app, lifespan, HTTP routes |

---

## Quick Start (local)

### Prerequisites

- Python 3.11+
- Redis running on `localhost:6379`
- Phase 1 model-gateway running on `localhost:11430`

```bash
cd orchestration/workflow-engine

# 1. copy env
cp .env.example .env

# 2. install deps
pip install -r requirements-dev.txt

# 3. run
uvicorn app.main:app --port 11431 --reload
```

API docs: http://localhost:11431/docs

---

## Quick Start (Docker Compose)

```bash
cd orchestration/workflow-engine

# starts redis + orchestration engine
docker compose up --build
```

> **Note**: Phase 1 model-gateway must be reachable at `http://host.docker.internal:11430`.
> On Linux you may need `extra_hosts: - "host.docker.internal:host-gateway"` in docker-compose.yml.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `MODEL_GATEWAY_URL` | `http://localhost:11430` | Phase 1 model-gateway base URL |
| `GATEWAY_MODEL` | `llama3.2:3b` | Model used for decomposition + summarisation |
| `ACTIVITY_LOG_DIR` | `./logs` | Directory for `activity.jsonl` |
| `APPROVAL_TIMEOUT_SECONDS` | `300` | Seconds before an approval times out |

---

## API Reference

### Health

```
GET /healthz
→ {"status": "ok", "redis": true}
```

### Tasks

```
POST /tasks
Content-Type: application/json

{
  "goal": "Find the current Bitcoin price and save it to /tmp/btc.txt",
  "policy": "default",
  "priority": "normal"
}

→ 202 TaskRecord
```

```
GET /tasks
→ {"tasks": [TaskRecord, ...]}

GET /tasks/{task_id}
→ TaskRecord  (404 if not found)
```

#### TaskRecord status values

| Status | Meaning |
|---|---|
| `queued` | Received, not yet started |
| `decomposing` | LLM decomposing goal into subtasks |
| `running` | Sub-tasks executing |
| `waiting_approval` | Blocked on human approval |
| `completed` | All subtasks done |
| `failed` | One or more subtasks failed |

### Approvals

```
GET /approvals/pending
→ {"pending": [ApprovalRecord, ...]}

POST /approvals/submit
Content-Type: application/json

{
  "approval_id": "<uuid>",
  "approved": true,
  "reviewer_note": "Looks safe"
}

→ ApprovalRecord  (404 if not found)
```

---

## Approval Policies

Set `policy` in the task request:

| Policy | Effect |
|---|---|
| `default` | No approvals required |
| `require_approval_for_shell` | All `shell` `run` actions need approval |
| `require_approval_for_browser` | Mutating browser actions need approval |
| `strict` | Shell `run` + browser mutations + file `write`/`delete` all need approval |

---

## Running Tests

```bash
cd orchestration/workflow-engine
python -m pytest tests/ -v
```

Test modules:

| File | Covers |
|---|---|
| `tests/test_dag.py` | DAG logic: deps, cycles, parallel nodes, diamond |
| `tests/test_approvals.py` | Approval store: request/approve/reject/timeout |
| `tests/test_decomposition.py` | Conductor._decompose: JSON parsing, fallback, dep translation |
| `tests/test_routing.py` | Redis Streams publish/read/ack, approval gating end-to-end |

---

## Activity Log

All events are written to `logs/activity.jsonl` as newline-delimited JSON:

```json
{"event": "task_start", "ts": "2024-01-15T10:00:00.000Z", "task_id": "...", "goal": "..."}
{"event": "subtask_start", "ts": "...", "task_id": "...", "subtask_id": "...", "agent_type": "shell"}
{"event": "subtask_complete", "ts": "...", "task_id": "...", "subtask_id": "..."}
{"event": "task_complete", "ts": "...", "task_id": "..."}
```
