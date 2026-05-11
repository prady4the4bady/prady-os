# Lumyn Agent (Phase 5)

Primary conversational AI service for PradyOS.

## Endpoints

- `POST /chat` `{ session_id, message, context? }`
- `GET /sessions`
- `DELETE /sessions/{id}`
- `POST /execute` `{ goal, auto_approve }`
- `POST /memory/search` `{ query, top_k }`

## Local Run

```bash
cd agents/lumyn
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
# source .venv/bin/activate

pip install -r requirements-dev.txt
uvicorn app.main:app --host 0.0.0.0 --port 11436 --reload
```

## Tests

```bash
cd agents/lumyn
pytest tests -v
```
