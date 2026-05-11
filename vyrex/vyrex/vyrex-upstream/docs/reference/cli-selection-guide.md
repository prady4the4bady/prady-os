---
title:
  page: "CLI Selection Guide"
  nav: "CLI Selection Guide"
description:
  main: "Choose between the Vyrex CLI and the OpenShell CLI for common sandbox operations."
  agent: "Explains when to use `vyrex` versus `openshell` for Vyrex-managed sandboxes, including lifecycle, inference, policy, monitoring, file transfer, and gateway operations."
keywords: ["vyrex vs openshell", "which cli", "vyrex cli", "openshell cli", "sandbox commands"]
topics: ["generative_ai", "ai_agents"]
tags: ["openclaw", "openshell", "vyrex", "cli", "sandboxing"]
content:
  type: reference
  difficulty: technical_beginner
  audience: ["developer", "engineer"]
status: published
---

<!--
  SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
  SPDX-License-Identifier: Apache-2.0
-->

# CLI Selection Guide

Vyrex uses two host-side CLIs.
Use `vyrex` for Vyrex-managed workflows.
Use `openshell` when you need a lower-level OpenShell operation that Vyrex intentionally exposes.

## Rule of Thumb

If the task changes how Vyrex creates, rebuilds, preserves, or configures a sandbox, start with `vyrex`.

If the task inspects or changes the live OpenShell gateway, TUI, raw policy, port forwarding, inference route, or sandbox file transfer, use `openshell`.

Do not create or recreate Vyrex-managed sandboxes directly with `openshell sandbox create` unless you intend to manage OpenShell yourself.
Run `vyrex onboard` afterward if you need to return to a Vyrex-managed environment.

## Use `vyrex` For Vyrex Workflows

Use `vyrex` for operations where Vyrex adds product-specific state, safety checks, backup behavior, credential handling, or OpenClaw configuration.

- Install, onboard, or recreate a Vyrex sandbox:

  ```console
  $ vyrex onboard
  $ vyrex onboard --resume --recreate-sandbox
  ```

- List, connect to, check, or delete Vyrex-managed sandboxes:

  ```console
  $ vyrex list
  $ vyrex my-assistant connect
  $ vyrex my-assistant status
  $ vyrex my-assistant logs --follow
  $ vyrex my-assistant destroy
  ```

- Rebuild or upgrade while preserving workspace state:

  ```console
  $ vyrex my-assistant rebuild
  $ vyrex upgrade-sandboxes --check
  ```

- Snapshot, restore, or mount sandbox state:

  ```console
  $ vyrex my-assistant snapshot create --name before-change
  $ vyrex my-assistant snapshot restore before-change
  $ vyrex my-assistant share mount
  ```

- Add or remove Vyrex policy presets:

  ```console
  $ vyrex my-assistant policy-add pypi --yes
  $ vyrex my-assistant policy-list
  $ vyrex my-assistant policy-remove pypi --yes
  ```

- Manage Vyrex messaging channels, credentials, diagnostics, and cleanup:

  ```console
  $ vyrex my-assistant channels add slack
  $ vyrex credentials list
  $ vyrex credentials reset nvidia-prod
  $ vyrex debug --sandbox my-assistant
  $ vyrex gc --dry-run
  ```

## Use `openshell` For OpenShell Operations

Use `openshell` when the docs explicitly call for a live OpenShell gateway operation or when you need a lower-level view beneath the Vyrex wrapper.

- Open the OpenShell TUI for network approvals and live activity:

  ```console
  $ openshell term
  ```

- Change the live gateway inference route:

  ```console
  $ openshell inference set -g vyrex --provider <provider> --model <model>
  $ openshell inference get -g vyrex
  ```

- Manage dashboard or service port forwards:

  ```console
  $ openshell forward start --background <port> <sandbox-name>
  $ openshell forward list
  ```

- Inspect the underlying sandbox state:

  ```console
  $ openshell sandbox list
  $ openshell sandbox get <sandbox-name>
  $ openshell logs <sandbox-name> --tail
  ```

- Run one-off commands or move files without starting a Vyrex chat session:

  ```console
  $ openshell sandbox exec -n <sandbox-name> -- ls -la /sandbox
  $ openshell sandbox upload <sandbox-name> ./local-file /sandbox/
  $ openshell sandbox download <sandbox-name> /sandbox/output ./output
  ```

- Inspect or replace raw OpenShell policy:

  ```console
  $ openshell policy get --full <sandbox-name> > live-policy.yaml
  $ openshell policy update <sandbox-name> --add-endpoint api.example.com:443:read-only:rest:enforce
  $ openshell policy set --policy live-policy.yaml <sandbox-name>
  ```

`openshell policy update` merges specific endpoint and rule changes into the live sandbox policy.
`openshell policy set` replaces the live policy with the file you provide.
For normal Vyrex network access changes, prefer `vyrex <name> policy-add` so Vyrex preserves presets and records the change for rebuilds.

## Common Decisions

This section covers common decisions when using the Vyrex CLI and the OpenShell CLI.

### First Setup or Full Recreate

Use `vyrex onboard`.
It starts the OpenShell gateway when needed, registers providers, builds the OpenClaw sandbox image, applies Vyrex policy choices, and creates the sandbox.

Avoid running `openshell gateway start --recreate` or `openshell sandbox create` directly for Vyrex-managed sandboxes.
Those commands do not update Vyrex's registry, session metadata, workspace-preservation flow, or OpenClaw-specific configuration.

### Connect to the Sandbox

Use `vyrex <name> connect` for an interactive Vyrex sandbox shell.
It waits for readiness, handles stale SSH host keys after gateway restarts, and prints agent-specific hints.

Use `openshell sandbox connect <name>` only when you intentionally want the raw OpenShell connection path.

For a one-off command, use `openshell sandbox exec` instead of opening an interactive shell.

```console
$ openshell sandbox exec -n my-assistant -- cat /tmp/gateway.log
```

### Check Health or Logs

Use `vyrex <name> status` and `vyrex <name> logs` first.
They combine Vyrex registry data, OpenShell state, OpenClaw process health, inference health, policy details, and messaging-channel warnings.

Use `openshell sandbox list`, `openshell sandbox get`, or `openshell logs` when debugging lower-level OpenShell behavior.

### Approve Blocked Network Requests

Use `openshell term`.
The OpenShell TUI owns live network activity and operator approval prompts.

Approved endpoints are session-scoped unless you also add them to the policy through a Vyrex preset or raw OpenShell policy update.

### Change Models or Providers

For a same-provider model switch, change the live OpenShell inference route:

```console
$ openshell inference set -g vyrex --provider nvidia-prod --model nvidia/nemotron-3-super-120b-a12b
```

For a provider-family change or a build-time OpenClaw setting change, rerun onboarding so the sandbox configuration is recreated consistently:

```console
$ vyrex onboard --resume --recreate-sandbox
```

Verify either path with:

```console
$ vyrex <name> status
```

### Update Network Policy

Use `vyrex <name> policy-add` or `policy-remove` for Vyrex presets and custom preset files.
Vyrex merges the new policy with the live policy and reapplies presets during rebuilds.

Use `openshell policy update` for precise live endpoint or REST rule changes.
Use `openshell policy get --full` and `openshell policy set` only when you need to edit and replace the raw policy file.

### Move Workspace Files

Use `vyrex <name> snapshot create`, `snapshot restore`, or `share mount` for normal workspace preservation and editing.

Use `openshell sandbox upload` and `openshell sandbox download` for manual file copies when you need exact control over source and destination paths.

## Related Topics

- [Commands](commands.md) for the full Vyrex command reference.
- [Manage Sandbox Lifecycle](../manage-sandboxes/lifecycle.md) for day-two operations.
- [Switch Inference Models](../inference/switch-inference-providers.md) for inference route examples.
- [Customize the Network Policy](../network-policy/customize-network-policy.md) for persistent network access changes.
- [Approve or Deny Network Requests](../network-policy/approve-network-requests.md) for the OpenShell TUI approval flow.
