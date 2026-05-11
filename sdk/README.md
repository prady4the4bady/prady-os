# Kryos SDK

The Kryos SDK is the app ecosystem contract for third-party developers building sandboxed apps for Prady OS. Apps declare a manifest, request explicit capabilities, and can be delegated work by the Kryos agent when they advertise matching functionality.

## Quick Start

1. Create a `kryos.app.json` manifest that matches `sdk/kryos.sdk.schema.json`.
2. Write your app and expose `POST /kryos/task` plus `GET /health`.
3. Package the app in a Docker image or local sandbox.
4. Install it from the Kryos App Store developer tab using a manifest URL or pasted JSON.
5. Test delegation by asking Kryos to use one of the app's capabilities.

## Manifest Reference

Required fields:
- `name`, `display_name`, `version`, `description`, `author`, `license`
- `entry_point`, `icon`, `permissions`, `capabilities`, `sandbox`, `ui`, `min_kryos_version`

Permissions:
- `model-inference`
- `file-system:read`
- `file-system:write`
- `computer-use`
- `notifications`
- `audio-input`
- `audio-output`
- `network`
- `task-schedule`

Capabilities use the `verb:noun` convention such as `send:email`, `search:web`, or `play:music`.

Sandbox defaults and limits:
- `memory_mb`: 64 to 2048
- `cpu_shares`: 64 to 1024
- `network_isolated`: boolean
- `read_only_root`: must be `true`

UI types:
- `window`
- `widget`
- `background`

## TypeScript SDK

- `PraxAgent.assignTask(description, options?)`
- `PraxAgent.getTaskStatus(taskId)`
- `PraxAgent.listSkills()`
- `KryosModel.query(prompt, options?)`
- `KryosModel.listModels()`
- `KryosFS.read(relativePath)`
- `KryosFS.write(relativePath, content)`
- `KryosFS.list(relativePath)`
- `KryosFS.delete(relativePath)`
- `KryosNotify.send(title, body, severity?)`
- `KryosTask.schedule(description, runAt, options?)`
- `KryosTask.cancel(scheduleId)`
- `KryosTask.list()`

## Python SDK

The Python package mirrors the TypeScript API with async `httpx` wrappers under `kryos_sdk`.

## Security Model

Apps run in Docker sandboxes with a read-only root filesystem, explicit permissions, and a constrained workspace under `/home/user/kryos-apps/<app_id>/`.

## Publishing

Host a public manifest URL, point the App Store at it, and ensure your image tag and entry point match the manifest.

## Example Apps

See `sdk/example-apps/` for a reference `weather-app` implementation.
