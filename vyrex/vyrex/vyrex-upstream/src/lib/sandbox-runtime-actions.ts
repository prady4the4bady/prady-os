// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/* v8 ignore start -- transitional action facade until implementations leave src/vyrex.ts. */

import type { SandboxConnectOptions } from "./vyrex-runtime-bridge";
import { getVyrexRuntimeBridge } from "./vyrex-runtime-bridge";

export async function connectSandbox(
  sandboxName: string,
  options?: SandboxConnectOptions,
): Promise<void> {
  await getVyrexRuntimeBridge().sandboxConnect(sandboxName, options);
}

export async function showSandboxStatus(sandboxName: string): Promise<void> {
  await getVyrexRuntimeBridge().sandboxStatus(sandboxName);
}

export function showSandboxLogs(sandboxName: string, follow: boolean): void {
  const { showSandboxLogs: showSandboxLogsAction } = require("./sandbox-logs-action") as {
    showSandboxLogs: (sandboxName: string, follow: boolean) => void;
  };
  showSandboxLogsAction(sandboxName, follow);
}

export async function destroySandbox(sandboxName: string, args: string[] = []): Promise<void> {
  await getVyrexRuntimeBridge().sandboxDestroy(sandboxName, args);
}

export async function rebuildSandbox(sandboxName: string, args: string[] = []): Promise<void> {
  await getVyrexRuntimeBridge().sandboxRebuild(sandboxName, args);
}

export async function installSandboxSkill(
  sandboxName: string,
  args: string[] = [],
): Promise<void> {
  await getVyrexRuntimeBridge().sandboxSkillInstall(sandboxName, args);
}

export async function runSandboxSnapshot(sandboxName: string, args: string[]): Promise<void> {
  await getVyrexRuntimeBridge().sandboxSnapshot(sandboxName, args);
}
