# Changelog

All notable changes to this project are documented in this file.

## v1.0.0 — Phase 39 — 2026-05-13 "Prax Invents"

### Added: Prax Inventor Engine
- Prax now discovers unsolved problems autonomously by scanning ArXiv, HackerNews, GitHub Trending, and ProductHunt every 6 hours using Lumyn reasoning
- Proposal card system: Prax presents one honest proposal showing problem, impact, tools, time estimate, confidence level, and honest caveats
- User sees exactly two buttons: Build It / Not Interested
- 6-agent build pipeline: Architect → Developer → QA → Documenter → Verifier
- VerifierAgent runs cold-start Docker verification before any project is delivered
- Projects are never released if verification fails
- Automatic GitHub push and release creation
- Inventor Dashboard UI with live build progress
- Full SQLite persistence for proposals and projects
- FilesystemBrain tiered file access zones (FREE/ASK/NEVER)

### Services added
- inventor-engine (port 8022)

### Tests
- 47 new tests across all inventor-engine modules

### Gates verified
- Gate 1: Python syntax — 0 errors
- Gate 2: Inventor tests — 47 passed, 0 failed
- Gate 3: Full regression — 0 failed, 0 errors
- Gate 4: TypeScript strict — EXIT:0
- Gate 5: ESLint — 0 warnings
- Gate 6: Dev compose — inventor-engine present
- Gate 7: Prod compose — valid config
- Gate 8: Shell scripts — all 3 clean
- Gate 9: Old names — 14/14 clean
- Gate 10: Smoke test — requires Docker Desktop

## v1.0.0 - 2026-05-11

### Added

- New system health service with:
  - `/health`
  - `/api/system/about`
  - `/api/system/health`
- Dev and prod compose wiring for system health in runtime dependencies
- ISO signing flow with checksum manifest and optional detached GPG signature
- Release workflow publish job for tagged releases
- Desktop shell actions for About and First Boot Wizard event handling

### Changed

- Canonical naming migration to:
  - Prady OS
  - Kryos
  - Prax Agent
  - Vyrex
  - Lumyn Agent
- ISO naming and release messaging updated to v1.0.0 conventions
- Build and CI artifact paths aligned with release outputs
- Gate validation scripts and tests aligned with release closure requirements

### Fixed

- Pytest import/collision handling across hyphenated platform service folders
- Desktop shell TypeScript and ESLint regressions in MenuBar/AppStore integration
- Post-rename Python package path consistency (`kryos_sdk`, `vyrex_proxy`, `vyrex.runtime`)
- Build/ISO test regressions caused by renamed expected files

### Validation Snapshot

- `python -m pytest ... -W error::DeprecationWarning -q --tb=short`
  - 710 passed, 2 skipped, 8 warnings, 0 failed
- TypeScript/ESLint gates:
  - desktop shell strict typecheck: pass
  - desktop shell eslint max warnings 0: pass
  - SDK strict typecheck: pass
- Compose/script syntax gates:
  - dev compose config: pass
  - prod compose config: pass
  - build/sign/write shell syntax: pass
- Gate 9 canonical old-name scan:
  - clean for the required legacy term set
- Gate 10 runtime smoke:
  - requires Docker Desktop on the Windows host

### Notes

- Gate 10 remains environment-dependent and must be executed manually on a host with Docker Desktop running.

