// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/* v8 ignore start -- transitional action facade until implementations leave src/vyrex.ts. */

import { getVyrexRuntimeBridge } from "./vyrex-runtime-bridge";

export async function addSandboxPolicy(sandboxName: string, args: string[] = []): Promise<void> {
  await getVyrexRuntimeBridge().sandboxPolicyAdd(sandboxName, args);
}

export async function removeSandboxPolicy(sandboxName: string, args: string[] = []): Promise<void> {
  await getVyrexRuntimeBridge().sandboxPolicyRemove(sandboxName, args);
}

export function listSandboxPolicies(sandboxName: string): void {
  getVyrexRuntimeBridge().sandboxPolicyList(sandboxName);
}

export function listSandboxChannels(sandboxName: string): void {
  getVyrexRuntimeBridge().sandboxChannelsList(sandboxName);
}

export async function addSandboxChannel(sandboxName: string, args: string[] = []): Promise<void> {
  await getVyrexRuntimeBridge().sandboxChannelsAdd(sandboxName, args);
}

export async function removeSandboxChannel(
  sandboxName: string,
  args: string[] = [],
): Promise<void> {
  await getVyrexRuntimeBridge().sandboxChannelsRemove(sandboxName, args);
}

export async function startSandboxChannel(
  sandboxName: string,
  args: string[] = [],
): Promise<void> {
  await getVyrexRuntimeBridge().sandboxChannelsStart(sandboxName, args);
}

export async function stopSandboxChannel(sandboxName: string, args: string[] = []): Promise<void> {
  await getVyrexRuntimeBridge().sandboxChannelsStop(sandboxName, args);
}
