# Vyrex Model Gateway

OpenAI-compatible API gateway that routes requests to local (Ollama) or cloud (OpenAI/Anthropic) backends according to a configurable routing policy.

**Default address:** `http://localhost:11430/v1`

---

## Quick Start

### Local (no Docker)

```bash
cd ai-core/model-gateway

# Create and activate virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and edit env file
cp .env.example .env

# Start the gateway
uvicorn app.main:app --host 0.0.0.0 --port 11430 --reload
```

### Docker (gateway only, Ollama must be running externally)

```bash
docker compose up model-gateway
```

### Docker (full stack including Ollama)

```bash
docker compose --profile full up
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GATEWAY_ROUTING_MODE` | *(from config)* | Override routing mode: `local-first`, `local-only`, `cloud-only` |
| `GATEWAY_CONFIG_DIR` | `./config` | Path to directory containing `routing-policy.yaml` and `model-registry.yaml` |
| `GATEWAY_LOG_DIR` | `./logs` | Directory where `audit.jsonl` is written |
| `OPENAI_API_KEY` | — | OpenAI API key (required for cloud backends) |
| `ANTHROPIC_API_KEY` | — | Anthropic API key (required for cloud backends) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Base URL for the Ollama service |

---

## Routing Modes

| Mode | Behaviour |
|---|---|
| `local-first` | Try Ollama first; on failure fall back to cloud providers in `fallback_order` |
| `local-only` | Send only to Ollama; never fall back to cloud |
| `cloud-only` | Skip Ollama; use cloud providers in `fallback_order` only |

Set in `config/routing-policy.yaml` or override at runtime with the `GATEWAY_ROUTING_MODE` environment variable.

---

## API Endpoints

### `GET /healthz`

Returns gateway health status.

```json
{"status": "ok", "ts": 1700000000}
```

### `GET /v1/models`

Lists all models in the registry.

```json
{
  "object": "list",
  "data": [
    {"id": "llama3.2:3b", "object": "model", "owned_by": "kryos"},
    {"id": "gpt-4o", "object": "model", "owned_by": "openai"}
  ]
}
```

### `POST /v1/chat/completions`

OpenAI-compatible chat completion. Accepts the same payload as the OpenAI Chat API.

```bash
curl http://localhost:11430/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.2:3b",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### `POST /v1/completions`

Text completion endpoint. Internally converts to a chat request.

---

## Model Registry

Models are defined in `config/model-registry.yaml`. Each entry has:

- `id` — model identifier (e.g. `llama3.2:3b`)
- `provider` — `ollama`, `openai`, or `anthropic`
- `capabilities` — list (e.g. `[chat, completion]`)
- `privacy_level` — `private` (local) or `cloud`
- `latency_profile` — `fast`, `medium`, or `slow`

---

## Audit Log

Every request and response is appended as a JSON line to `logs/audit.jsonl`.

**Request event:**

```json
{"event": "request", "ts": "2024-01-01T00:00:00Z", "correlation_id": "...", "endpoint": "chat/completions", "model": "llama3.2:3b", "policy_mode": "local-first", "backends_to_try": ["ollama", "openai"]}
```

**Response event:**

```json
{"event": "response", "ts": "2024-01-01T00:00:00Z", "correlation_id": "...", "backend": "ollama", "success": true, "model": "llama3.2:3b", "latency_ms": 312.4}
```

Each HTTP request carries an `X-Correlation-ID` header (generated if absent) that links request and response audit records.

---

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

---

## Project Structure

```
ai-core/model-gateway/
├── app/
│   ├── __init__.py
│   ├── audit.py        # JSONL audit logger
│   ├── config.py       # YAML config loader + RoutingPolicyConfig
│   ├── gateway.py      # ModelGateway: dispatch loop + backend adapters
│   ├── main.py         # FastAPI app, lifespan, routes
│   ├── middleware.py   # Correlation ID middleware
│   ├── policy.py       # RoutingPolicyEngine
│   ├── registry.py     # ModelRegistry
│   └── schemas.py      # Pydantic v2 OpenAI-compatible schemas
├── config/
│   ├── model-registry.yaml
│   └── routing-policy.yaml
├── tests/
│   ├── conftest.py
│   ├── test_audit.py
│   ├── test_gateway.py
│   ├── test_policy.py
│   └── test_registry.py
├── logs/               # audit.jsonl written here at runtime
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── requirements-dev.txt
```
