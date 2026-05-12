# Prady OS v1.0.0

**Repository:** https://github.com/prady4the4bady/prady-os  
**License:** MIT  
**Built by:** Pradyun — Dubai, UAE — 2026

## What This Release Is

A working Linux desktop distribution with a 34-service AI stack that
runs local-first through Ollama (with cloud API fallback) and a build
pipeline that produces a signed bootable ISO.

## What's In It

| Component | Role |
|-----------|------|
| **Prady OS** | Linux desktop distribution (Buildroot-based, Wayland / Hyprland compositor) |
| **Kryos** | Multi-agent swarm orchestration engine (`orchestration/kryos-swarm`) |
| **Prax** | Autonomous AI agent — React loop over plan / act / observe (`prax-agent` + `agent-runtime` + `computer-use` + `automation-service`) |
| **Lumyn** | Deep reasoning sub-agent used by Prax (`agents/lumyn`) |
| **Vyrex** | AI inference proxy — OpenAI-compatible gateway over local Ollama and cloud APIs (`vyrex-proxy` + `ai-core/model-gateway`) |
| 34 platform microservices | Auth, memory, scheduler, watchdog, OTA, BIOS AI, notification bus, audit log, etc. |
| Desktop shell | GTK / React shell with dock, mission control, launcher, OOBE wizard |
| CI pipelines | `Monorepo CI`, `E2E`, `Build Prady OS ISO` |

## Installation

### From ISO

```bash
# Download from GitHub Releases
curl -L https://github.com/prady4the4bady/prady-os/releases/download/v1.0.0/prady-os.iso \
    -o prady-os.iso

# Verify checksum
curl -L https://github.com/prady4the4bady/prady-os/releases/download/v1.0.0/prady-os.sha256 \
    -o prady-os.sha256
sha256sum -c prady-os.sha256

# Write to USB
sudo dd if=prady-os.iso of=/dev/sdX bs=4M status=progress
```

Boot from the USB and follow the installer. The OOBE wizard runs on
first login.

### From Source (Development)

```powershell
docker compose -f docker-compose.dev.yml up -d --build
pwsh build/smoke_test.ps1
```

Expected: `Results: 34 / 34 services healthy`.

## Verification

v1.0.0 was verified with:

- **Python syntax:** 0 errors across all tracked `.py` files
- **pytest:** 188 tests across model-gateway, workflow-engine, screen-agent, lumyn, ISO build config — all passing
- **docker compose config:** base, dev, prod all valid
- **smoke_test.ps1:** 34 / 34 services healthy
- **CI:** `Monorepo CI` green, `E2E` green, `Build Prady OS ISO / validate` green

## System Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | x86-64, AVX2 | Modern 8-core |
| RAM | 8 GB | 16 GB (for local LLM) |
| Disk | 20 GB | 60 GB (for model cache) |
| GPU | Not required (CPU inference works) | NVIDIA + CUDA 12 for Ollama acceleration |
| Firmware | UEFI | UEFI with SecureBoot |

## Honest Limitations (Read Before Flashing)

v1.0.0 is a solid foundation, not the full autonomous OS vision. What
is explicitly **not** in this release:

- **Continuous background research.** The `kryos-researcher` service
  that ingests arXiv, RSS, and GitHub trending into memory is planned
  for v1.1 and not present here.
- **Full project proposal pipeline.** The "OS proposes a project → you
  approve → OS executes plan → build → test → deploy → promote" flow
  is partial. The React loop can execute a scripted goal; the
  autonomous project lifecycle is v1.2.
- **OOBE credential validation.** The wizard collects keys but does
  not yet validate them against each provider before continuing. v1.1.
- **Intel Arc / AMD GPU local inference.** v1.0 is tested with NVIDIA
  CUDA via Ollama. Other accelerators are v1.2.
- **"Privacy-first" = local-first.** If you set `OPENAI_API_KEY` or
  `ANTHROPIC_API_KEY` in `.env`, Vyrex will route to those providers
  when the local model is unavailable. Remove the keys for fully
  on-device operation.

## Changelog Highlights

- 34 platform microservices wired together and smoke-tested end to end
- Full canonical name sweep — no predecessor product names anywhere
  in the tree (see `refactor: canonical rename sweep` commit)
- Buildroot-based ISO pipeline, tag-gated in CI, producing signed
  `prady-os.iso` + `.sha256` + `.sig`
- Three CI workflows: `Monorepo CI`, `E2E`, `Build Prady OS ISO`,
  all green with zero deprecation warnings on runners
- Typer 0.12 CLI issue worked around in `model-manager` by invoking
  `uvicorn prady_models.platform_api:app` (now `prady_models...`) directly
- Agent-runtime, kryos-swarm, model-manager, and the 7 auth-middleware
  services fixed so every container stays up across the stack

## Security

Report vulnerabilities per `SECURITY.md`. Secrets never ship inside
container images; they are injected via `.env` at runtime.

## License

MIT. Third-party dependencies retain their own licenses.
