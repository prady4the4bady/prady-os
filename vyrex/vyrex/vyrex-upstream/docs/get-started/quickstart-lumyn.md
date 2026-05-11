---
title:
  page: "Vyrex Quickstart with Lumyn"
  nav: "Vyrex Quickstart with Lumyn"
description:
  main: "Install Vyrex, select the Lumyn agent, and launch a sandboxed Lumyn API endpoint."
  agent: "Installs Vyrex, selects the Lumyn agent, and launches a sandboxed Lumyn API endpoint. Use when users ask for Lumyn setup, VyrexLumyn onboarding, or running Lumyn inside OpenShell."
keywords: ["vyrex-lumyn quickstart", "lumyn agent vyrex", "run lumyn openshell sandbox"]
topics: ["generative_ai", "ai_agents"]
tags: ["lumyn", "openshell", "sandboxing", "inference_routing", "vyrex"]
content:
  type: get_started
  difficulty: technical_beginner
  audience: ["developer", "engineer"]
skill:
  priority: 20
status: published
---

<!--
  SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
  SPDX-License-Identifier: Apache-2.0
-->

# Vyrex Quickstart with Lumyn

Use VyrexLumyn when you want Vyrex to create an OpenShell sandbox that runs Lumyn instead of the default OpenClaw agent.
The `vyrex-lumyn` command is an alias for `vyrex` with the Lumyn agent pre-selected.

:::{warning}
The Lumyn agent option is experimental.
Interfaces, defaults, and supported features may change without notice, and it is not recommended for production use.
:::

Review the [Prerequisites](prerequisites.md) before starting.
The first Lumyn build can take several minutes because Vyrex builds the Lumyn sandbox base image if it is not already cached.

## Install and Onboard

Start the installer with `VYREX_AGENT=lumyn` set in your shell.
The installer installs the CLI, selects the `vyrex-lumyn` alias, and runs the guided onboarding flow.

```console
$ export VYREX_AGENT=lumyn
$ curl -fsSL https://www.nvidia.com/vyrex.sh | bash
```

If Vyrex is already installed, start Lumyn onboarding directly.

```console
$ vyrex-lumyn onboard
```

## Respond to the Wizard

The onboard wizard asks for a sandbox name, inference provider, model, credentials, and network policy preset.
At any prompt, press Enter to accept the default shown in `[brackets]`, type `back` to return to the previous prompt, or type `exit` to quit.

The default Lumyn sandbox name is `lumyn`.
Use a distinct sandbox name, such as `my-lumyn`, so you can run Lumyn and OpenClaw sandboxes side by side.
Vyrex prevents same-name reuse when an existing sandbox uses a different agent.

```text
Sandbox name [lumyn]: my-lumyn
```

Choose the inference provider that matches where you want Lumyn model traffic to go.
The provider options and credential environment variables are the same as the standard Vyrex quickstart.
For provider-specific prompts, refer to the [Respond to the Onboard Wizard](quickstart.md#respond-to-the-onboard-wizard) section and the [Inference Options](../inference/inference-options.md) page.
The Lumyn wizard does not ask for Brave Web Search because Lumyn does not use Vyrex's OpenClaw web-search configuration.

After provider and policy selection, review the summary and confirm the build.
Vyrex writes Lumyn configuration into `/sandbox/.lumyn`, routes model traffic through `inference.local`, and starts the Lumyn gateway inside the sandbox.
The Lumyn image includes runtime dependencies for the supported Vyrex messaging integrations, API service, and health endpoint.
The base image does not include unsupported Lumyn integrations.

## Use Non-Interactive Setup

For CI or scripted installs, set the required environment variables before running the installer.
The example below uses NVIDIA Endpoints and creates a sandbox named `my-lumyn`.

```console
$ export VYREX_AGENT=lumyn
$ export VYREX_NON_INTERACTIVE=1
$ export VYREX_ACCEPT_THIRD_PARTY_SOFTWARE=1
$ export VYREX_SANDBOX_NAME=my-lumyn
$ export NVIDIA_API_KEY=<your-key>
$ curl -fsSL https://www.nvidia.com/vyrex.sh | bash
```

Use the provider variables from [Inference Options](../inference/inference-options.md) when you choose a different provider.

## Connect to Lumyn

When onboarding completes, Vyrex prints the sandbox name, model, lifecycle commands, and Lumyn API endpoint.
Lumyn exposes an OpenAI-compatible API on port `8642`, not a browser dashboard.

```text
──────────────────────────────────────────────────
Sandbox      my-lumyn (Landlock + seccomp + netns)
Model        nvidia/nemotron-3-super-120b-a12b (NVIDIA Endpoints)
──────────────────────────────────────────────────
Run:         vyrex-lumyn my-lumyn connect
Status:      vyrex-lumyn my-lumyn status
Logs:        vyrex-lumyn my-lumyn logs --follow

Lumyn Agent OpenAI-compatible API
Port 8642 must be forwarded before connecting.
http://127.0.0.1:8642/v1
──────────────────────────────────────────────────
```

To chat with the agent from a terminal, follow these steps:

1. Connect to the sandbox and start the Lumyn CLI.

   ```console
   $ vyrex-lumyn my-lumyn connect
   ```

2. Inside the sandbox, run the Lumyn CLI.

   ```console
   $ lumyn
   ```

## Check the API Endpoint

The onboard flow starts the port forward automatically.
Check the health endpoint from the host to confirm that the Lumyn API is reachable.

```console
$ curl -sf http://127.0.0.1:8642/health
```

If the command cannot connect after a reboot or terminal restart, start the forward again.

```console
$ openshell forward start --background 8642 my-lumyn
```

Configure an OpenAI-compatible client with the base URL `http://127.0.0.1:8642/v1`.
Lumyn uses API header authentication for client requests.
Do not append an OpenClaw `#token=` URL fragment to the Lumyn endpoint.

## Manage the Sandbox

Use the same lifecycle commands as a standard Vyrex sandbox.
The `vyrex-lumyn` alias keeps help text and recovery messages aligned with Lumyn, while targeting the same registered sandbox.
`vyrex list` shows the agent type for each sandbox so you can distinguish Lumyn and OpenClaw entries.

```console
$ vyrex-lumyn my-lumyn status
$ vyrex-lumyn my-lumyn logs --follow
$ vyrex-lumyn my-lumyn snapshot create --name before-change
$ vyrex-lumyn my-lumyn rebuild
```

To change the active model or provider without rebuilding the sandbox, use the OpenShell inference route.

```console
$ openshell inference set -g vyrex --model <model> --provider <provider>
```

To remove the sandbox when you are done, destroy it explicitly.

```console
$ vyrex-lumyn my-lumyn destroy
```

## Next Steps

- [Inference Options](../inference/inference-options.md) to choose a provider and model.
- [Commands](../reference/commands.md) to see the full `vyrex-lumyn` alias behavior.
- [Backup and Restore](../manage-sandboxes/backup-restore.md) to preserve sandbox state before destructive operations.
- [Monitor Sandbox Activity](../monitoring/monitor-sandbox-activity.md) to inspect OpenShell events and sandbox logs.
