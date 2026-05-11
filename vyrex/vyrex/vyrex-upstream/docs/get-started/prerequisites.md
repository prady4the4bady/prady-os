---
title:
  page: "Vyrex Prerequisites"
  nav: "Prerequisites"
description:
  main: "Hardware, software, and supported platforms for running Vyrex."
  agent: "Lists the hardware, software, and container runtime requirements for running Vyrex. Use when verifying prerequisites before installation."
keywords: ["vyrex prerequisites", "vyrex supported platforms", "vyrex hardware software"]
topics: ["generative_ai", "ai_agents"]
tags: ["openclaw", "openshell", "sandboxing", "vyrex"]
content:
  type: reference
  difficulty: technical_beginner
  audience: ["developer", "engineer"]
status: published
---

<!--
  SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
  SPDX-License-Identifier: Apache-2.0
-->

# Prerequisites

Before getting started, check the prerequisites to ensure you have the necessary software and hardware to run Vyrex.

## Hardware

| Resource | Minimum        | Recommended      |
|----------|----------------|------------------|
| CPU      | 4 vCPU         | 4+ vCPU          |
| RAM      | 8 GB           | 16 GB            |
| Disk     | 20 GB free     | 40 GB free       |

The sandbox image is approximately 2.4 GB compressed. During image push, the Docker daemon, k3s, and the OpenShell gateway run alongside the export pipeline. The pipeline buffers decompressed layers in memory. On machines with less than 8 GB of RAM, this combined usage can trigger the OOM killer. If you cannot add memory, configuring at least 8 GB of swap can work around the issue at the cost of slower performance.

## Software

| Dependency | Version                          |
|------------|----------------------------------|
| Node.js    | 22.16 or later |
| npm        | 10 or later |
| Platform   | See [Platforms](#platforms) below |

:::{warning} OpenShell Lifecycle
For Vyrex-managed environments, use `vyrex onboard` when you need to create or recreate the OpenShell gateway or sandbox.
Avoid `openshell self-update`, `npm update -g openshell`, `openshell gateway start --recreate`, or `openshell sandbox create` directly unless you intend to manage OpenShell separately and then rerun `vyrex onboard`.
:::

:::{note} Docker storage driver
On Linux hosts running Docker 26 or later with the [containerd image store](https://docs.docker.com/engine/storage/containerd/) enabled (the install-time default for fresh `docker-ce` installations on Ubuntu 24.04 and similar distros), `vyrex onboard` transparently builds a `fuse-overlayfs`-enabled cluster image to bypass a kernel-level nested-overlay limitation in k3s.
No manual setup is required.
See the [troubleshooting guide](../reference/troubleshooting.md) for the override knobs and a manual `daemon.json` alternative.
:::

## Platforms

The following table lists tested platform and runtime combinations.
Availability is not limited to these entries, but untested configurations can have issues.
The table is generated from [`ci/platform-matrix.json`](https://github.com/NVIDIA/Vyrex/blob/main/ci/platform-matrix.json), the single source of truth kept in sync by CI and QA.

```{include} ../../README.md
:start-after: <!-- platform-matrix:begin -->
:end-before: <!-- platform-matrix:end -->
```

## Next Steps

- [Prepare Windows for Vyrex](windows-preparation.md) if you are using Windows.
- [Quickstart](quickstart.md) to install Vyrex and launch your first sandbox.

```{toctree}
:maxdepth: 1
:hidden:

windows-preparation
```
