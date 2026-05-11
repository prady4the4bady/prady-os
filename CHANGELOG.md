# Changelog

All notable changes to this project are documented in this file.

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
  - 708 passed, 2 skipped, 7 warnings, 0 failed
- TypeScript/ESLint gates:
  - desktop shell strict typecheck: pass
  - desktop shell eslint max warnings 0: pass
  - SDK strict typecheck: pass
- Compose/script syntax gates:
  - dev compose config: pass
  - prod compose config: pass
  - build/sign/write shell syntax: pass
- Gate 9 canonical old-name scan:
  - clean for required term set

### Notes

- Gate 10 remains environment-dependent and must be executed manually on a host with Docker Desktop running.
