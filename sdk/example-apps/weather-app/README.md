# Weather App Example

This example shows the contract every Kryos SDK app must implement.

## Run

```bash
uvicorn main:app --reload --port 8080
```

## Endpoints

- `POST /kryos/task` handles delegated SDK tasks.
- `GET /health` reports app status.

## Manifest

The included `kryos.app.json` is valid against `sdk/kryos.sdk.schema.json` and can be installed through the Kryos App Store developer flow.
