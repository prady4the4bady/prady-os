---
title:
  page: "Deploy Vyrex to a Remote GPU Instance with Brev"
  nav: "Deploy to Remote GPU"
description:
  main: "Run Vyrex on a remote GPU instance and understand the legacy Brev compatibility flow."
  agent: "Explains how to run Vyrex on a remote GPU instance, including the deprecated Brev compatibility path and the preferred installer plus onboard flow. Use when deploying Vyrex to a remote VM, onboarding a Brev instance, or migrating away from the legacy `vyrex deploy` wrapper."
keywords: ["deploy vyrex remote gpu", "vyrex brev cloud deployment"]
topics: ["generative_ai", "ai_agents"]
tags: ["openclaw", "openshell", "deployment", "gpu", "vyrex"]
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

# Deploy Vyrex to a Remote GPU Instance

Run Vyrex on a remote GPU instance through [Brev](https://brev.nvidia.com).
The preferred path is to provision the VM, run the standard Vyrex installer on that host, and then run `vyrex onboard`.

## Quick Start

If your Brev instance is already up and has already been onboarded with a sandbox, start with the standard sandbox chat flow:

```console
$ vyrex my-assistant connect
$ openclaw tui
```

This gets you into the sandbox shell first and opens the OpenClaw chat UI right away.
If the VM is fresh, run the standard installer on that host and then run `vyrex onboard` before trying `vyrex my-assistant connect`.

If you are connecting from your local machine and still need to provision the remote VM, you can still use `vyrex deploy <instance-name>` as the legacy compatibility path described below.

## Prerequisites

- The [Brev CLI](https://brev.nvidia.com) installed and authenticated.
- A provider credential for the inference backend you want to use during onboarding.
- `HF_TOKEN` or `HUGGING_FACE_HUB_TOKEN` exported when your remote vLLM or Hugging Face workflow needs access to gated models.
- Vyrex installed locally if you plan to use the deprecated `vyrex deploy` wrapper. Otherwise, install Vyrex directly on the remote host after provisioning it.

## Deploy the Instance

:::{warning}
The `vyrex deploy` command is deprecated.
Prefer provisioning the remote host separately, then running the standard Vyrex installer and `vyrex onboard` on that host.
:::

Create a Brev instance and run the legacy compatibility flow:

```console
$ vyrex deploy <instance-name>
```

Replace `<instance-name>` with a name for your remote instance, for example `my-gpu-box`.

The legacy compatibility flow performs the following steps on the VM:

1. Installs Docker and the NVIDIA Container Toolkit if a GPU is present.
2. Installs the OpenShell CLI.
3. Runs `vyrex onboard` (the setup wizard) to create the gateway, register providers, and launch the sandbox.
4. Starts optional host auxiliary services (for example the cloudflared tunnel) when `cloudflared` is available. Channel messaging is configured during onboarding and runs through OpenShell-managed processes, not through `vyrex tunnel start`.

By default, the compatibility wrapper asks Brev to provision on `gcp`. Override this with `VYREX_BREV_PROVIDER` if you need a different Brev cloud provider.
If you export `HF_TOKEN` or `HUGGING_FACE_HUB_TOKEN`, the wrapper forwards those values to the VM so remote setup can pull gated Hugging Face model repositories.

## Connect to the Remote Sandbox

After deployment finishes, the deploy command opens an interactive shell inside the remote sandbox.
To reconnect after closing the session, run the command again:

```console
$ vyrex deploy <instance-name>
```

## Monitor the Remote Sandbox

SSH to the instance and run the OpenShell TUI to monitor activity and approve network requests:

```console
$ ssh <instance-name> 'cd ~/vyrex && set -a && . .env && set +a && openshell term'
```

## Verify Inference

Run a test agent prompt inside the remote sandbox:

```console
$ openclaw agent --agent main --local -m "Hello from the remote sandbox" --session-id test
```

## Remote Dashboard Access

The Vyrex dashboard validates the browser origin against an allowlist baked
into the sandbox image at build time.  By default the allowlist only contains
`http://127.0.0.1:18789`.  When accessing the dashboard from a remote browser
(for example through a Brev public URL or an SSH port-forward), set
`CHAT_UI_URL` to the origin the browser will use **before** running setup:

```console
$ export CHAT_UI_URL="https://openclaw0-<id>.brevlab.com"
$ vyrex deploy <instance-name>
```

For SSH port-forwarding, the origin is typically `http://127.0.0.1:18789` (the
default), so no extra configuration is needed.

:::{warning}
On Brev, set `CHAT_UI_URL` in the launchable environment configuration so it is
available when the installer builds the sandbox image. If `CHAT_UI_URL` is not
set on a headless host, the compatibility wrapper prints a warning.

`VYREX_DISABLE_DEVICE_AUTH` is also evaluated at image build time.
When `CHAT_UI_URL` points at a non-loopback origin, Vyrex disables OpenClaw device pairing in the generated sandbox configuration because browser-only remote users cannot complete terminal-based pairing.
Any device that can reach the configured dashboard origin can connect without pairing, so avoid exposing that origin on internet-reachable or shared-network deployments.
:::

## Proxy Configuration

Vyrex routes sandbox traffic through a gateway proxy that defaults to `10.200.0.1:3128`.
If your network requires a different proxy, set `VYREX_PROXY_HOST` and `VYREX_PROXY_PORT` before onboarding:

```console
$ export VYREX_PROXY_HOST=proxy.example.com
$ export VYREX_PROXY_PORT=8080
$ vyrex onboard
```

These values are baked into the sandbox image at build time.
They are also forwarded into the runtime container during sandbox creation, so `/tmp/vyrex-proxy-env.sh` uses the same host and port that the image build used.
Only alphanumeric characters, dots, hyphens, and colons are accepted for the host.
The port must be numeric (0-65535).
Changing the proxy after onboarding requires re-running `vyrex onboard`.

## GPU Configuration

The deploy script uses the `VYREX_GPU` environment variable to select the GPU type.
The default value is `a2-highgpu-1g:nvidia-tesla-a100:1`.
Set this variable before running `vyrex deploy` to use a different GPU configuration:

```console
$ export VYREX_GPU="a2-highgpu-1g:nvidia-tesla-a100:2"
$ vyrex deploy <instance-name>
```

## Related Topics

- [Set Up Messaging Channels](../manage-sandboxes/messaging-channels.md) to connect Telegram, Discord, or Slack through OpenShell-managed channel messaging.
- [Monitor Sandbox Activity](../monitoring/monitor-sandbox-activity.md) for sandbox monitoring tools.
- [Commands](../reference/commands.md) for the full `deploy` command reference.
