// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Handler for the /vyrex slash command (chat interface).
 *
 * Supports subcommands:
 *   /vyrex status   - show sandbox/blueprint/inference state
 *   /vyrex eject    - rollback to host installation
 *   /vyrex shields  - show shields status (read-only)
 *   /vyrex config   - show sandbox config (read-only, redacted)
 *   /vyrex          - show help
 */

import type { PluginCommandContext, PluginCommandResult, OpenClawPluginApi } from "../index.js";
import { loadState } from "../blueprint/state.js";
import {
  describeOnboardEndpoint,
  describeOnboardProvider,
  loadOnboardConfig,
} from "../onboard/config.js";
import { slashShieldsStatus } from "./shields-status.js";
import { slashConfigShow } from "./config-show.js";

export function handleSlashCommand(
  ctx: PluginCommandContext,
  _api: OpenClawPluginApi,
): PluginCommandResult {
  const subcommand = ctx.args?.trim().split(/\s+/)[0] ?? "";

  switch (subcommand) {
    case "status":
      return slashStatus();
    case "eject":
      return slashEject();
    case "onboard":
      return slashOnboard();
    case "shields":
      return slashShieldsStatus();
    case "config":
      return slashConfigShow();
    default:
      return slashHelp();
  }
}

function slashHelp(): PluginCommandResult {
  return {
    text: [
      "**Vyrex**",
      "",
      "Usage: `/vyrex <subcommand>`",
      "",
      "Subcommands:",
      "  `status`  - Show sandbox, blueprint, and inference state",
      "  `shields` - Show shields status (up/down, timeout, policy)",
      "  `config`  - Show sandbox configuration (credentials redacted)",
      "  `eject`   - Show rollback instructions",
      "  `onboard` - Show onboarding status and instructions",
      "",
      "For full management use the Vyrex CLI:",
      "  `vyrex <name> shields down|up|status`",
      "  `vyrex <name> config get`",
      "  `vyrex <name> status`",
      "  `vyrex <name> connect`",
      "  `vyrex <name> logs`",
      "  `vyrex <name> destroy`",
    ].join("\n"),
  };
}

function slashStatus(): PluginCommandResult {
  const state = loadState();

  if (!state.lastAction) {
    return {
      text: "**Vyrex**: No operations performed yet. Run `vyrex onboard` to get started.",
    };
  }

  const lines = [
    "**Vyrex Status**",
    "",
    `Last action: ${state.lastAction}`,
    `Blueprint: ${state.blueprintVersion ?? "unknown"}`,
    `Run ID: ${state.lastRunId ?? "none"}`,
    `Sandbox: ${state.sandboxName ?? "none"}`,
    `Updated: ${state.updatedAt}`,
  ];

  if (state.migrationSnapshot) {
    lines.push("", `Rollback snapshot: ${state.migrationSnapshot}`);
  }

  if (state.lastRebuildAt) {
    lines.push("", `Last rebuild: ${state.lastRebuildAt}`);
    if (state.lastRebuildBackupPath) {
      lines.push(`Rebuild backup: ${state.lastRebuildBackupPath}`);
    }
  }

  return { text: lines.join("\n") };
}

function slashOnboard(): PluginCommandResult {
  const config = loadOnboardConfig();
  if (config) {
    return {
      text: [
        "**Vyrex Onboard Status**",
        "",
        `Endpoint: ${describeOnboardEndpoint(config)}`,
        `Provider: ${describeOnboardProvider(config)}`,
        config.ncpPartner ? `NCP Partner: ${config.ncpPartner}` : null,
        `Model: ${config.model}`,
        `Credential: $${config.credentialEnv}`,
        `Profile: ${config.profile}`,
        `Onboarded: ${config.onboardedAt}`,
        "",
        "To reconfigure, run: `vyrex onboard`",
      ]
        .filter(Boolean)
        .join("\n"),
    };
  }
  return {
    text: [
      "**Vyrex Onboarding**",
      "",
      "No configuration found. Run the onboard command to set up inference:",
      "",
      "```",
      "vyrex onboard",
      "```",
    ].join("\n"),
  };
}

function slashEject(): PluginCommandResult {
  const state = loadState();

  if (!state.lastAction) {
    return { text: "No Vyrex deployment found. Nothing to eject from." };
  }

  if (!state.migrationSnapshot && !state.hostBackupPath) {
    return {
      text: "No migration snapshot found. Manual rollback required.",
    };
  }

  return {
    text: [
      "**Eject from Vyrex**",
      "",
      "To rollback to your host OpenClaw installation, run:",
      "",
      "```",
      "vyrex <name> destroy",
      "```",
      "",
      `Snapshot: ${state.migrationSnapshot ?? state.hostBackupPath ?? "none"}`,
    ].join("\n"),
  };
}
