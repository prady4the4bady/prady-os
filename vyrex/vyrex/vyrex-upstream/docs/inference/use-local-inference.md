---
title:
  page: "Use a Local Inference Server with Vyrex"
  nav: "Use Local Inference"
description:
  main: "Connect Vyrex to a local model server such as Ollama, vLLM, TensorRT-LLM, or any OpenAI-compatible endpoint."
  agent: "Connects Vyrex to a local inference server. Use when setting up Ollama, vLLM, TensorRT-LLM, NIM, or any OpenAI-compatible local model server with Vyrex."
keywords: ["vyrex local inference", "ollama vyrex", "vllm vyrex", "local model server", "openai compatible endpoint"]
topics: ["generative_ai", "ai_agents"]
tags: ["openclaw", "openshell", "inference_routing", "local_inference"]
content:
  type: how_to
  difficulty: intermediate
  audience: ["developer", "engineer"]
skill:
  priority: 10
status: published
---

<!--
  SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
  SPDX-License-Identifier: Apache-2.0
-->

# Use a Local Inference Server

Vyrex can route inference to a model server running on your machine instead of a cloud API.
This page covers Ollama, compatible-endpoint paths for other servers, and two experimental options for vLLM and NVIDIA NIM.

All approaches use the same `inference.local` routing model.
The agent inside the sandbox never connects to your model server directly.
OpenShell intercepts inference traffic and forwards it to the local endpoint you configure.

## Prerequisites

- Vyrex installed.
  Refer to the [Quickstart](../get-started/quickstart.md) if you have not installed yet.
- A local model server running, or Ollama installed. The Vyrex onboard wizard can also start Ollama for you.

## Ollama

Ollama is the default local inference option.
The onboard wizard detects Ollama automatically when it is installed or running on the host.

If Ollama is not running, Vyrex starts it for you.
On macOS, the wizard also offers to install Ollama through Homebrew if it is not present.

Run the onboard wizard.

```console
$ vyrex onboard
```

Select **Local Ollama** from the provider list.
Vyrex lists installed models or offers starter models if none are installed.
It pulls the selected model, loads it into memory, and validates it before continuing.
On WSL, if Ollama is running on the Windows host, Vyrex pulls missing models through the Ollama HTTP API instead of requiring the `ollama` CLI inside WSL.

### Authenticated Reverse Proxy

Vyrex keeps Ollama bound to `127.0.0.1:11434` and starts a token-gated
reverse proxy on `0.0.0.0:11435`.
Containers and other hosts on the local network reach Ollama only through the
proxy, which validates a Bearer token before forwarding requests.
Ollama itself is never exposed without authentication.

The onboard wizard manages the proxy automatically:

- Generates a random 24-byte token on first run and stores it in
  `~/.vyrex/ollama-proxy-token` with `0600` permissions.
- Starts the proxy after Ollama and verifies it before continuing.
- Cleans up stale proxy processes from previous runs.
- Retries the sandbox container reachability check and can continue when the host-side proxy is healthy even if the container probe fails.
- Reuses the persisted token after a host reboot so you do not need to re-run
  onboard.

The sandbox provider is configured to use proxy port `11435` with the generated
token as its `OPENAI_API_KEY` credential.
OpenShell's L7 proxy injects the token at egress, so the agent inside the
sandbox never sees the token directly.

`GET /api/tags` is exempt from authentication so container health checks
continue to work.
All other endpoints (including `POST /api/tags`) require the Bearer token.

If Ollama is already running on a non-loopback address when you start onboard,
the wizard restarts it on `127.0.0.1:11434` so the proxy is the only network
path to the model server.

### GPU Memory Cleanup

When you switch away from Ollama, stop host services, or destroy an Ollama-backed sandbox, Vyrex asks Ollama to unload currently loaded models from GPU memory.
The cleanup sends `keep_alive: 0` for each model reported by Ollama and runs on a best-effort basis, so shutdown continues if Ollama is already stopped.
This does not delete downloaded model files.

### Non-Interactive Setup

```console
$ VYREX_PROVIDER=ollama \
  VYREX_MODEL=qwen2.5:14b \
  vyrex onboard --non-interactive
```

If `VYREX_MODEL` is not set, Vyrex selects a default model based on available memory.

| Variable | Purpose |
|---|---|
| `VYREX_PROVIDER` | Set to `ollama`. |
| `VYREX_MODEL` | Ollama model tag to use. Optional. |

## OpenAI-Compatible Server

This option works with any server that implements `/v1/chat/completions`, including vLLM, TensorRT-LLM, llama.cpp, LocalAI, and others.
For compatible endpoints, Vyrex uses `/v1/chat/completions` by default.
This avoids a class of failures where local backends accept `/v1/responses` requests but silently drop the system prompt and tool definitions.
To opt in to `/v1/responses`, set `VYREX_PREFERRED_API=openai-responses` before running onboard.

Start your model server.
The examples below use vLLM, but any OpenAI-compatible server works.

```console
$ vllm serve meta-llama/Llama-3.1-8B-Instruct --port 8000
```

Run the onboard wizard.

```console
$ vyrex onboard
```

When the wizard asks you to choose an inference provider, select **Other OpenAI-compatible endpoint**.
Enter the base URL of your local server, for example `http://localhost:8000/v1`.

The wizard prompts for an API key.
If your server does not require authentication, enter any non-empty string (for example, `dummy`).

Vyrex validates the endpoint by sending a test inference request before continuing.
The wizard probes `/v1/chat/completions` by default for the compatible-endpoint provider.
If you set `VYREX_PREFERRED_API=openai-responses`, Vyrex probes `/v1/responses` instead and only selects it when the response includes the streaming events OpenClaw requires.

### Non-Interactive Setup

Set the following environment variables for scripted or CI/CD deployments.

```console
$ VYREX_PROVIDER=custom \
  VYREX_ENDPOINT_URL=http://localhost:8000/v1 \
  VYREX_MODEL=meta-llama/Llama-3.1-8B-Instruct \
  COMPATIBLE_API_KEY=dummy \
  vyrex onboard --non-interactive
```

| Variable | Purpose |
|---|---|
| `VYREX_PROVIDER` | Set to `custom` for an OpenAI-compatible endpoint. |
| `VYREX_ENDPOINT_URL` | Base URL of the local server. |
| `VYREX_MODEL` | Model ID as reported by the server. |
| `COMPATIBLE_API_KEY` | API key for the endpoint. Use any non-empty value if authentication is not required. |

### Selecting the API Path

For the compatible-endpoint provider, `/v1/chat/completions` is the default.
Vyrex tests streaming events during onboarding and uses chat completions
without probing the Responses API.

To opt in to `/v1/responses`, set `VYREX_PREFERRED_API` before running onboard:

```console
$ VYREX_PREFERRED_API=openai-responses vyrex onboard
```

The wizard then probes `/v1/responses` and only selects it when streaming
support is complete.
If the probe fails, the wizard falls back to `/v1/chat/completions`
automatically.
You can use this variable in both interactive and non-interactive mode.

| Variable | Values | Default |
|---|---|---|
| `VYREX_PREFERRED_API` | `openai-completions`, `openai-responses` | `openai-completions` for compatible endpoints |

If you already onboarded and the sandbox is failing at runtime, re-run
`vyrex onboard` to re-probe the endpoint and bake the correct API path
into the image.
Refer to [Switch Inference Models](switch-inference-providers.md) for details.

## Anthropic-Compatible Server

If your local server implements the Anthropic Messages API (`/v1/messages`), choose **Other Anthropic-compatible endpoint** during onboarding instead.

```console
$ vyrex onboard
```

For non-interactive setup, use `VYREX_PROVIDER=anthropicCompatible` and set `COMPATIBLE_ANTHROPIC_API_KEY`.

```console
$ VYREX_PROVIDER=anthropicCompatible \
  VYREX_ENDPOINT_URL=http://localhost:8080 \
  VYREX_MODEL=my-model \
  COMPATIBLE_ANTHROPIC_API_KEY=dummy \
  vyrex onboard --non-interactive
```

## vLLM Auto-Detection (Experimental)

When vLLM is already running on `localhost:8000`, Vyrex can detect it automatically and query the `/v1/models` endpoint to determine the loaded model.

Set the experimental flag and run onboard.

```console
$ VYREX_EXPERIMENTAL=1 vyrex onboard
```

Select **Local vLLM [experimental]** from the provider list.
Vyrex detects the running model and validates the endpoint.

:::{note}
Vyrex forces the `chat/completions` API path for vLLM.
The vLLM `/v1/responses` endpoint does not run the `--tool-call-parser`, so tool calls arrive as raw text.
:::

### Non-Interactive Setup

```console
$ VYREX_EXPERIMENTAL=1 \
  VYREX_PROVIDER=vllm \
  vyrex onboard --non-interactive
```

Vyrex auto-detects the model from the running vLLM instance.
To override the model, set `VYREX_MODEL`.

## NVIDIA NIM (Experimental)

Vyrex can pull, start, and manage a NIM container on hosts with a NIM-capable NVIDIA GPU.

Set the experimental flag and run onboard.

```console
$ VYREX_EXPERIMENTAL=1 vyrex onboard
```

Select **Local NVIDIA NIM [experimental]** from the provider list.
Vyrex filters available models by GPU VRAM, pulls the NIM container image, starts it, and waits for it to become healthy before continuing.

NIM container images are hosted on `nvcr.io` and require NGC registry authentication before `docker pull` succeeds.
If Docker is not already logged in to `nvcr.io`, onboard prompts for an [NGC API key](https://org.ngc.nvidia.com/setup/api-key) and runs `docker login nvcr.io` over `--password-stdin` so the key is never written to disk or shell history.
The prompt masks the key during input and retries once on a bad key before failing.
In non-interactive mode, onboard exits with login instructions if Docker is not already authenticated; run `docker login nvcr.io` yourself, then re-run `vyrex onboard --non-interactive`.

:::{note}
NIM uses vLLM internally.
The same `chat/completions` API path restriction applies.
:::

### Non-Interactive Setup

```console
$ VYREX_EXPERIMENTAL=1 \
  VYREX_PROVIDER=nim \
  vyrex onboard --non-interactive
```

To select a specific model, set `VYREX_MODEL`.

## Timeout Configuration

Local inference requests use a default timeout of 180 seconds.
Large prompts on hardware such as DGX Spark can exceed shorter timeouts, so Vyrex sets a higher default for Ollama, vLLM, NIM, and compatible-endpoint setup.

To override the timeout, set the `VYREX_LOCAL_INFERENCE_TIMEOUT` environment variable before onboarding:

```console
$ export VYREX_LOCAL_INFERENCE_TIMEOUT=300
$ vyrex onboard
```

The value is in seconds.
This setting is baked into the sandbox at build time.
Changing it after onboarding requires re-running `vyrex onboard`.

## Verify the Configuration

After onboarding completes, confirm the active provider and model.

```console
$ vyrex <name> status
```

The output shows the provider label (for example, "Local vLLM" or "Other OpenAI-compatible endpoint") and the active model.

## Switch Models at Runtime

You can change the model without re-running onboard.
Refer to [Switch Inference Models](switch-inference-providers.md) for the full procedure.

For compatible endpoints, the command is:

```console
$ openshell inference set --provider compatible-endpoint --model <model-name>
```

If the provider itself needs to change (for example, switching from vLLM to a cloud API), rerun `vyrex onboard`.

## Next Steps

- [Inference Options](inference-options.md) for the full list of providers available during onboarding.
- [Switch Inference Models](switch-inference-providers.md) for runtime model switching.
- [Quickstart](../get-started/quickstart.md) for first-time installation.
