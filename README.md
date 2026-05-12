# Prady OS

Prady OS is a Linux-based desktop distribution that integrates a long-running
AI workforce directly into the OS. The idea is simple: the OS can research,
plan, and execute software projects on its own, and you — the user — act as
the approver and final reviewer.

Built by Pradyun — Dubai, UAE — 2026.
License: MIT. See [`LICENSE`](LICENSE).

## What's Shipping Today (v1.0.0)

These are the components that exist in this release, tested locally, and
verified by the smoke suite. No simulation — each one is a real service
with a real job.

| Component | Role | Status |
|-----------|------|--------|
| **Kryos** | Multi-agent swarm orchestration engine | Running as `kryos-swarm` service |
| **Prax** | The autonomous AI agent (plan → act → observe loop) | Running as `agent-runtime` + `computer-use` + `automation-service` |
| **Lumyn** | Deep reasoning sub-agent inside Prax | Running as `agents/lumyn` FastAPI service |
| **Vyrex** | AI inference proxy (Ollama local + cloud passthrough) | Running as `vyrex-proxy` + `ai-core/model-gateway` |
| **34 platform services** | Auth, memory, scheduler, watchdog, OTA, BIOS AI, etc. | All green on the smoke suite |
| **Desktop shell** | GTK-based shell with dock, mission control, launcher | Running as `desktop-shell` service |
| **Production ISO build** | Buildroot pipeline producing `prady-os.iso` | Tag-gated CI job on `v*` |
| **Smoke test** | `pwsh build/smoke_test.ps1` | 34/34 passing |

The claim line for v1.0.0 is intentionally narrow:

> A working Linux desktop distribution with a 34-service AI stack that
> runs local-first through Ollama, with cloud API fallback, and a build
> pipeline that produces a signed bootable ISO.

## What's on the Roadmap (Honest About What's Not Done Yet)

The full vision — an OS that continuously researches ideas and brings
approved projects through plan → build → test → deploy → promote without
human micromanagement — is a multi-release effort. Here is where each
piece actually stands today.

| Capability | v1.0.0 state |
|------------|--------------|
| Continuous background research (arxiv, GitHub trending, RSS → memory) | Not shipped. Planned for v1.1 as the `kryos-researcher` service. |
| Project proposal + notification → user approval pipeline | Not shipped. State machine and UI are on the v1.1 backlog. |
| Autonomous plan → build → test | Partial. Prax can run a scripted goal via the React loop; real multi-stage autonomy is v1.2. |
| Deploy + promote (publish, marketing, distribution) | Not shipped. v1.3 target. |
| OOBE wizard with per-provider credential validation | Stubs only. The wizard boots; validation is v1.1. |
| GPU-accelerated local inference on Intel Arc / AMD | v1.0 ships NVIDIA via Ollama; Intel/AMD is v1.2. |

If something isn't in the "Shipping Today" table, treat it as planned,
not built.

## Architecture

```
PRADY OS
└── KRYOS  (multi-agent swarm orchestration engine)
    └── PRAX  (autonomous AI agent)
        ├── LUMYN  (deep reasoning sub-agent)
        └── VYREX  (AI inference proxy)
            ├── Local: Ollama + HuggingFace models
            └── Cloud: OpenAI-compatible passthrough
```

Full service inventory, dependency chain, and fallback strategy live in
[`ARCHITECTURE.md`](ARCHITECTURE.md).

## Repository Layout

```
ai-core/        Model gateway (OpenAI-compatible LLM router)
orchestration/  Kryos swarm + workflow engine
agents/         Lumyn reasoning sub-agent
automation/     Screen agent, playwright runner
platform/       34 microservices (auth, memory, scheduler, watchdog, OTA, ...)
prax-agent/     Prax autonomous agent (TypeScript)
desktop/        Aqua desktop-shell frontend (React + Tauri)
ui/             Additional UI panels (OOBE wizard, desktop shell)
sdk/            Prady SDK (TypeScript + Python)
installer/      Live-build config, firstboot wizard assets
build/          ISO build scripts, grub assets, smoke test, release tooling
iso-build/      Buildroot overlay, systemd unit files for the built system
kernel/         Kernel patches (uinput, eBPF hardening)
packages/       systemd unit files published into the ISO
```

## Quick Local Validation

```powershell
# syntax + compose + lint
python -m pytest ai-core/model-gateway/tests orchestration/workflow-engine/tests `
    automation/screen-agent/tests agents/lumyn/tests build/iso/tests -q
docker compose -f docker-compose.dev.yml config --quiet
docker compose -f build/iso/docker-compose.prod.yml config --quiet
bash -n build/iso/scripts/build_iso.sh
bash -n build/iso/scripts/sign_iso.sh
bash -n build/iso/scripts/write_usb.sh

# bring the full 34-service stack up and smoke it
docker compose -f docker-compose.dev.yml up -d --build
pwsh build/smoke_test.ps1
```

Expected smoke result: `Results: 34 / 34 services healthy`.

## Build an ISO (Tagged Release Only)

The heavy Buildroot compile runs in CI only for `v*` tag pushes (see
`.github/workflows/build-iso.yml`). To build locally:

```bash
make -C build/iso iso-fast
```

Output: `output/prady-os.iso` with sha256 sidecar.

## Security

Report vulnerabilities per [`SECURITY.md`](SECURITY.md). The AI stack is
local-first: Vyrex prefers Ollama on the host and only calls cloud APIs
when explicit API keys are configured. There is no implicit telemetry.

## Privacy Note

"Local-first" does not mean "never touches the cloud". If you configure
an `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` in `.env`, Vyrex will use
those providers as fallback when the local model is unavailable. Remove
the keys to keep inference fully on-device.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). All PRs must pass the three
workflows (`Monorepo CI`, `E2E`, `Build Prady OS ISO` validate job)
before merge.

## Version

v1.0.0 — initial production release of the 34-service platform stack
and the signed ISO pipeline. Tagged at commit `00aefd4c` (pre-rename);
the post-rename canonical tree starts at the commit recorded on the
`v1.0.0` tag after the history rewrite.
