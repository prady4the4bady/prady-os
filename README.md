# Prady OS v1.0.0

Prady OS is a privacy-first, AI-native desktop operating system distribution with a modular platform stack and production-oriented release tooling.

## Highlights

- Desktop shell integration with About and First Boot Wizard flows
- Unified system health service endpoints for runtime and UI consumers
- Release ISO build and signing pipeline
- Multi-service local development stack
- 708+ automated tests passing

## Core Components

- Kryos: OS-level agent orchestration and platform integration
- Prax Agent: execution and workflow runtime agent surfaces
- Vyrex: model/runtime policy and routing subsystem
- Lumyn Agent: assistant-facing orchestration and control-plane behavior

## Repository Layout

- build: ISO build scripts, grub assets, release tests
- platform: Python microservices and platform APIs
- ui: desktop shell frontend and test handlers
- sdk: TypeScript and Python SDKs
- installer: first-boot and installation assets
- compositor, shell, firmware, kernel: desktop and low-level integration modules

## Quick Validation

From repo root:

```powershell
python -m pytest platform/ sdk/prady-sdk-python/tests build/iso/tests/ -W error::DeprecationWarning -q --tb=short
Set-Location ui/desktop-shell
npx --yes tsc --noEmit --strict
npx --yes eslint src/ --ext .ts,.tsx --max-warnings 0
Set-Location ../../sdk/prady-sdk
npx --yes tsc --noEmit --strict
Set-Location ../../
docker compose -f docker-compose.dev.yml config --quiet
docker compose -f build/iso/docker-compose.prod.yml config --quiet
bash -n build/iso/scripts/build_iso.sh
bash -n build/iso/scripts/sign_iso.sh
bash -n build/iso/scripts/write_usb.sh
```

## Release Status

- Version: v1.0.0
- Validation: 708 passed, 2 skipped, 0 failed
- Gates: 9/10 automated gates verified in-session
- Gate 10: manual Docker Desktop health smoke required on Windows host

## Manual Gate 10

1. Start Docker Desktop and wait until healthy.
2. Run `docker compose -f docker-compose.dev.yml up -d --wait`.
3. Probe `/health` for ports 8000,8001,8002,8003,8004,8005,8006,8007,8009,8010,8011,8012,8013,8014,8015,8017,8018,8019,8020,8021.
4. Run `docker compose -f docker-compose.dev.yml down`.

## Security

See SECURITY.md for supported versions, reporting guidance, and hardening notes.

## License

MIT. See LICENSE.
