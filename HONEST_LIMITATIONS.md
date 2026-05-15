# Honest Limitations — Prady OS v1.0.0

This document lists known limitations, stubs, and features that require specific hardware or credentials.
Nothing here is hidden. If Prax cannot verify a claim, it is documented here instead of being advertised.

## Features that require specific hardware

### BIOS AI (Phase 34)
The UEFI Stage 1 application (PradyBiosAI.c) is compiled and present in firmware/uefi-ai/ but has not
been tested on real UEFI hardware in CI. Stage 2 (post-boot repair) runs on Linux and is tested.
UEFI Stage 1 requires an x86_64 machine with UEFI firmware to verify end-to-end.
Fallback: if the UEFI AI application fails to load, standard GRUB boots normally without any impact.

### Computer-use (cursor and keyboard control)
Works on X11 via xdotool. Works on Wayland via ydotool (requires uinput kernel module and correct
permissions). Does not work inside Docker containers without a real display socket passed in.
In containers without display: returns {"success": false, "error": "no display available"}
and never crashes.

### Voice interface (Whisper + Piper)
Requires a microphone for speech-to-text. Requires speakers for text-to-speech.
In containers or machines without audio devices: Piper returns silence WAV bytes, Whisper returns
an empty transcript. Both fail gracefully without crashing.

## Features that are functional stubs

### LoRA fine-tuning (Phase 35)
The lora_trainer.py file exists and schedules fine-tuning sessions during idle periods. It calls
the Vyrex proxy /v1/fine-tune endpoint. However most local models served via Ollama do not expose
a fine-tune endpoint. When the endpoint returns 404, the trainer logs a warning and skips gracefully.
Actual LoRA weight updates require: a GPU, the unsloth or TRL library installed, and a base model
that supports fine-tuning via the API. Current behavior without GPU: scheduling works, actual weight
updates do not occur.

### GGML inference in UEFI (Phase 34)
The ModelRunner.c file in firmware/uefi-ai/ currently uses rule-based triage (RAM size, disk error
count) rather than a real quantized model. Full GGML inference inside UEFI requires a custom
llama.cpp port targeting the EDK2 runtime, which is not yet complete. The rules correctly identify
NORMAL, REPAIR, SAFE, and RECOVERY boot states for the most common hardware conditions.

## Features that require external credentials

### Social media publishing (Phase 40)
Twitter/X: TWITTER_BEARER_TOKEN, TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN,
           TWITTER_ACCESS_SECRET
Reddit:    REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD
ProductHunt: PRODUCTHUNT_API_KEY
HackerNews:  HN_USERNAME, HN_PASSWORD
Without credentials: each platform is skipped silently. Prady OS does not provide these credentials.
All API usage is via official free-tier endpoints only.

### GitHub auto-release (Phase 39)
Requires GITHUB_TOKEN with repo write scope. Without the token: projects are saved locally at
/var/prady/projects/ and a notification is sent explaining that GitHub push was skipped.
The token is never stored in the codebase.

## Performance notes

### Inventor engine project build times
Simple CLI tools: 2 to 4 hours estimated. Web applications: 8 to 16 hours estimated.
Complex systems: 24 to 48 hours estimated. All estimates are honest guesses based on project
complexity. Prax does not guarantee completion within any specific time. If a build exceeds
48 hours without completing, it is marked as failed and the user is notified honestly.

### Market intelligence data quality
GitHub star and fork counts are accurate (live API). npm weekly download counts are accurate
(live API). Market size estimates are NOT provided — we do not estimate without citing a
verifiable source. Competitor analysis is limited to public GitHub data and npm registry.
Private or unlisted products will not appear in competitor lists.

## Phase N+1 — Durable Memory + Durable Orchestration

### Ahnis embeddings are hash-based by default
The default embedding provider is `LocalHashProvider` which uses a deterministic SHA-256 hash-to-vector
projection (64-dim). This is NOT a learned semantic embedding — it does not capture meaning, only
token presence. When `sentence-transformers` is installed and `AHNIS_EMBEDDING_MODE` is set to
`sentence-transformer` or `auto`, Ahnis uses a real semantic embedding model (default:
all-MiniLM-L6-v2, 384-dim) with local-hash as fallback. Qdrant integration is optional and configured
via `QDRANT_HOST`. When Qdrant is available, vectors are stored locally in-memory regardless.

### Neila retry queue is SQLite-backed but single-node
The retry queue and scheduled actions are persisted to a local SQLite database (`NEILA_DB_PATH`,
default `/data/neila.db`). This survives container restarts but is not distributed. If Neila runs
on multiple replicas, each has its own queue. There is no leader election or distributed locking.
For single-node deployments (the current target), this is sufficient.

### Sentence Transformer provider requires separate dependency
The `sentence-transformers` Python package is NOT included in base dependencies because it pulls
in PyTorch (~2GB). Users who want semantic embeddings must install it separately:
```
pip install sentence-transformers
```
When the package is absent, Ahnis falls back to `LocalHashProvider` seamlessly. The provider
reports its actual availability in `/ahnis/embeddings/provider` and `/ahnis/status`.

### Repo-wide pytest requires per-suite execution
A single `python -m pytest platform/ ai-core/` command from the repo root fails because
service-level `tests/conftest.py` files from different subdirectories collide under the
`tests.conftest` namespace. The `platform/conftest.py` path-manipulation approach works for
`platform/`-only runs but conflicts when combined with `ai-core/` suites. The recommended
approach is to run each suite individually (via `scripts/run_all_tests.py`) or from the
service's own directory. Each suite uses its own conftest for path setup without collisions.

### Ahnis memory store is in-memory (not persisted to disk)
Memory entries live in Python dictionaries. Consolidation trims large categories but does not
write to disk. A full restart of the Ahnis service loses all in-memory entries. Qdrant, when
configured, provides persistent vector storage, but the metadata cache in Ahnis is still
in-memory. Production deployments should pair Ahnis with Qdrant or add a persister bridge.

## Honest limitations (continued)

### Self-learning improvement rate
The self-learning service tracks task success rates and stores successful action sequences as
skills. The improvement rate metric measures score changes over time. Without GPU-based LoRA
fine-tuning active, improvement comes from skill retrieval (reusing past successful patterns)
rather than weight updates. This is still useful — retrieved skills make Prax faster on similar
tasks — but it is not the same as gradient-based learning.
