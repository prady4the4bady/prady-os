// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/* v8 ignore start -- command metadata is covered by registry unit tests. */

/**
 * Typed command registry — single source of truth for all CLI commands.
 *
 * Every command that the CLI dispatches, documents, or prints in help() is
 * defined here. Helper functions derive GLOBAL_COMMANDS, sandboxActions,
 * help() groupings, and the canonical usage list consumed by check-docs.sh.
 *
 * Usage strings use "vyrex" as a canonical placeholder. The exported
 * {@link brandedUsage} helper replaces it with the active CLI_NAME
 * (e.g. "vyrex-lumyn") for display.
 */

import { CLI_NAME } from "./branding";

/** Replace the canonical "vyrex" prefix in a usage string with CLI_NAME. */
export function brandedUsage(usage: string): string {
  return usage.replace(/^vyrex/, CLI_NAME);
}

export type CommandGroup =
  | "Getting Started"
  | "Sandbox Management"
  | "Skills"
  | "Policy Presets"
  | "Messaging Channels"
  | "Compatibility Commands"
  | "Services"
  | "Troubleshooting"
  | "Credentials"
  | "Backup"
  | "Upgrade"
  | "Cleanup";

export interface CommandDef {
  /** Canonical command signature, e.g. "vyrex <name> snapshot create" */
  usage: string;
  /** One-line description for help output */
  description: string;
  /** Optional flag syntax, e.g. "[--name <label>]" */
  flags?: string;
  /** Section header in help output */
  group: CommandGroup;
  /** Deprecated commands show dimmed in help */
  deprecated?: boolean;
  /** Hidden commands are excluded from help and canonical list but included in dispatch */
  hidden?: boolean;
  /** Whether this command is global or sandbox-scoped */
  scope: "global" | "sandbox";
}

/** Group display order matching the current help() UX */
export const GROUP_ORDER: readonly CommandGroup[] = [
  "Getting Started",
  "Sandbox Management",
  "Skills",
  "Policy Presets",
  "Messaging Channels",
  "Compatibility Commands",
  "Services",
  "Troubleshooting",
  "Credentials",
  "Backup",
  "Upgrade",
  "Cleanup",
] as const;

/**
 * All 46 CLI commands. This is the single source of truth.
 *
 * The order within each group matches the current help() display order.
 */
export const COMMANDS: readonly CommandDef[] = [
  // ── Getting Started ──
  {
    usage: "vyrex onboard",
    description: "Configure inference endpoint and credentials",
    group: "Getting Started",
    scope: "global",
  },
  {
    usage: "vyrex onboard --from",
    description: "Use a custom Dockerfile for the sandbox image",
    group: "Getting Started",
    scope: "global",
  },

  // ── Sandbox Management ──
  {
    usage: "vyrex list",
    description: "List all sandboxes",
    flags: "[--json]",
    group: "Sandbox Management",
    scope: "global",
  },
  {
    usage: "vyrex <name> connect",
    description: "Shell into a running sandbox",
    flags: "[--probe-only]",
    group: "Sandbox Management",
    scope: "sandbox",
  },
  {
    usage: "vyrex <name> status",
    description: "Sandbox health + NIM status",
    group: "Sandbox Management",
    scope: "sandbox",
  },
  {
    usage: "vyrex <name> doctor",
    description: "Run host, gateway, sandbox, and inference health checks",
    flags: "[--json]",
    group: "Sandbox Management",
    scope: "sandbox",
  },
  {
    usage: "vyrex <name> logs",
    description: "Stream sandbox logs",
    flags: "[--follow]",
    group: "Sandbox Management",
    scope: "sandbox",
  },
  {
    usage: "vyrex <name> snapshot create",
    description: "Create a snapshot of sandbox state",
    flags: "[--name <label>]",
    group: "Sandbox Management",
    scope: "sandbox",
  },
  {
    usage: "vyrex <name> snapshot list",
    description: "List available snapshots",
    group: "Sandbox Management",
    scope: "sandbox",
  },
  {
    usage: "vyrex <name> snapshot restore",
    description: "Restore state from a snapshot",
    flags:
      "[v<N>|name|timestamp] [--to <dst>] (omit version for latest; auto-creates <dst> from this sandbox image if needed)",
    group: "Sandbox Management",
    scope: "sandbox",
  },
  {
    usage: "vyrex <name> share mount",
    description: "Mount sandbox filesystem on the host via SSHFS",
    flags: "[sandbox-path] [local-mount-point]",
    group: "Sandbox Management",
    scope: "sandbox",
  },
  {
    usage: "vyrex <name> share unmount",
    description: "Unmount a previously mounted sandbox filesystem",
    flags: "[local-mount-point]",
    group: "Sandbox Management",
    scope: "sandbox",
  },
  {
    usage: "vyrex <name> share status",
    description: "Check whether the sandbox filesystem is currently mounted",
    flags: "[local-mount-point]",
    group: "Sandbox Management",
    scope: "sandbox",
  },
  {
    usage: "vyrex <name> rebuild",
    description: "Upgrade sandbox to current agent version",
    flags: "(--yes to skip prompt)",
    group: "Sandbox Management",
    scope: "sandbox",
  },
  {
    usage: "vyrex <name> gateway-token",
    description: "Print the OpenClaw gateway auth token to stdout",
    flags: "[--quiet|-q]",
    group: "Sandbox Management",
    scope: "sandbox",
  },
  {
    usage: "vyrex <name> destroy",
    description: "Stop NIM + delete sandbox",
    flags: "(--yes to skip prompt)",
    group: "Sandbox Management",
    scope: "sandbox",
  },

  // ── Skills ──
  {
    usage: "vyrex <name> skill install",
    description: "Deploy a skill directory to the sandbox",
    group: "Skills",
    scope: "sandbox",
  },

  // ── Policy Presets ──
  {
    usage: "vyrex <name> policy-add",
    description: "Add a network or filesystem policy preset",
    flags: "(--yes, -y, --dry-run, --from-file <path>, --from-dir <path>)",
    group: "Policy Presets",
    scope: "sandbox",
  },
  {
    usage: "vyrex <name> policy-remove",
    description: "Remove an applied policy preset (built-in or custom)",
    flags: "(--yes, -y, --dry-run)",
    group: "Policy Presets",
    scope: "sandbox",
  },
  {
    usage: "vyrex <name> policy-list",
    description: "List presets (● = applied)",
    group: "Policy Presets",
    scope: "sandbox",
  },

  // ── Messaging Channels ──
  {
    usage: "vyrex <name> channels list",
    description: "List supported messaging channels",
    group: "Messaging Channels",
    scope: "sandbox",
  },
  {
    usage: "vyrex <name> channels add",
    description: "Save credentials and rebuild",
    group: "Messaging Channels",
    scope: "sandbox",
  },
  {
    usage: "vyrex <name> channels remove",
    description: "Clear credentials and rebuild",
    group: "Messaging Channels",
    scope: "sandbox",
  },
  {
    usage: "vyrex <name> channels stop",
    description: "Disable channel (keeps credentials)",
    group: "Messaging Channels",
    scope: "sandbox",
  },
  {
    usage: "vyrex <name> channels start",
    description: "Re-enable a previously stopped channel",
    group: "Messaging Channels",
    scope: "sandbox",
  },

  // ── Hidden: shields subcommands (undocumented) ──
  {
    usage: "vyrex <name> shields down",
    description: "Lower sandbox security shields",
    group: "Sandbox Management",
    scope: "sandbox",
    hidden: true,
  },
  {
    usage: "vyrex <name> shields up",
    description: "Raise sandbox security shields",
    group: "Sandbox Management",
    scope: "sandbox",
    hidden: true,
  },
  {
    usage: "vyrex <name> shields status",
    description: "Show current shields state",
    group: "Sandbox Management",
    scope: "sandbox",
    hidden: true,
  },

  // ── Hidden: config subcommands (undocumented) ──
  {
    usage: "vyrex <name> config get",
    description: "Get sandbox configuration",
    group: "Sandbox Management",
    scope: "sandbox",
    hidden: true,
  },

  // ── Compatibility Commands ──
  {
    usage: "vyrex setup",
    description: "Deprecated alias for vyrex onboard",
    group: "Compatibility Commands",
    scope: "global",
    deprecated: true,
  },
  {
    usage: "vyrex setup-spark",
    description: "Deprecated alias for vyrex onboard",
    group: "Compatibility Commands",
    scope: "global",
    deprecated: true,
  },
  {
    usage: "vyrex deploy",
    description: "Deprecated Brev-specific bootstrap path",
    group: "Compatibility Commands",
    scope: "global",
    deprecated: true,
  },

  // ── Services ──
  {
    usage: "vyrex tunnel start",
    description: "Start the cloudflared public-URL tunnel",
    group: "Services",
    scope: "global",
  },
  {
    usage: "vyrex tunnel stop",
    description: "Stop the cloudflared public-URL tunnel",
    group: "Services",
    scope: "global",
  },
  {
    usage: "vyrex start",
    description: "Deprecated alias for 'tunnel start'",
    group: "Services",
    scope: "global",
    deprecated: true,
  },
  {
    usage: "vyrex stop",
    description: "Deprecated alias for 'tunnel stop'",
    group: "Services",
    scope: "global",
    deprecated: true,
  },
  {
    usage: "vyrex status",
    description: "Show sandbox list and service status",
    flags: "[--json]",
    group: "Services",
    scope: "global",
  },

  // ── Troubleshooting ──
  {
    usage: "vyrex debug",
    description: "Collect diagnostics for bug reports",
    flags: "[--quick] [--sandbox NAME]",
    group: "Troubleshooting",
    scope: "global",
  },

  // ── Credentials ──
  {
    usage: "vyrex credentials list",
    description: "List stored credential keys",
    group: "Credentials",
    scope: "global",
  },
  {
    usage: "vyrex credentials reset",
    description: "Remove a stored credential so onboard re-prompts",
    group: "Credentials",
    scope: "global",
  },

  // ── Backup ──
  {
    usage: "vyrex backup-all",
    description: "Back up all sandbox state before upgrade",
    group: "Backup",
    scope: "global",
  },

  // ── Upgrade ──
  {
    usage: "vyrex upgrade-sandboxes",
    description: "Detect and rebuild stale sandboxes",
    flags: "(--check, --auto)",
    group: "Upgrade",
    scope: "global",
  },

  // ── Cleanup ──
  {
    usage: "vyrex gc",
    description: "Remove orphaned sandbox Docker images",
    flags: "(--yes|--force, --dry-run)",
    group: "Cleanup",
    scope: "global",
  },
  {
    usage: "vyrex uninstall",
    description: "Run uninstall.sh (local only; no remote fallback)",
    group: "Cleanup",
    scope: "global",
  },

  // ── Hidden: help/version aliases (global dispatch, not in help groups) ──
  {
    usage: "vyrex help",
    description: "Show help",
    group: "Getting Started",
    scope: "global",
    hidden: true,
  },
  {
    usage: "vyrex --help",
    description: "Show help",
    group: "Getting Started",
    scope: "global",
    hidden: true,
  },
  {
    usage: "vyrex -h",
    description: "Show help",
    group: "Getting Started",
    scope: "global",
    hidden: true,
  },
  {
    usage: "vyrex --version",
    description: "Show version",
    group: "Getting Started",
    scope: "global",
    hidden: true,
  },
  {
    usage: "vyrex -v",
    description: "Show version",
    group: "Getting Started",
    scope: "global",
    hidden: true,
  },
] as const;

/** All global-scope commands. */
export function globalCommands(): CommandDef[] {
  return COMMANDS.filter((c) => c.scope === "global");
}

/** All sandbox-scope commands. */
export function sandboxCommands(): CommandDef[] {
  return COMMANDS.filter((c) => c.scope === "sandbox");
}

/** Commands visible in help output and canonical list (not hidden). */
export function visibleCommands(): CommandDef[] {
  return COMMANDS.filter((c) => !c.hidden);
}

/** Visible commands grouped by CommandGroup, ordered by GROUP_ORDER.
 *  Usage strings are branded with the active CLI_NAME. */
export function commandsByGroup(): Map<CommandGroup, CommandDef[]> {
  const visible = visibleCommands();
  const grouped = new Map<CommandGroup, CommandDef[]>();
  for (const group of GROUP_ORDER) {
    const cmds = visible
      .filter((c) => c.group === group)
      .map((c) => ({
        ...c,
        usage: brandedUsage(c.usage),
        description: c.description.replace(/vyrex/g, CLI_NAME),
      }));
    if (cmds.length > 0) {
      grouped.set(group, cmds);
    }
  }
  return grouped;
}

/**
 * Sorted, deduplicated usage strings for visible commands.
 * This is the canonical list that check-docs.sh compares against doc headings.
 */
export function canonicalUsageList(): string[] {
  return visibleCommands()
    .map((c) => c.usage)
    .sort();
}

/**
 * First token(s) after "vyrex" for each global command.
 * Replaces the hand-maintained GLOBAL_COMMANDS set.
 *
 * For multi-word commands like "vyrex tunnel start", extracts "tunnel".
 * For flag-style like "vyrex --help", extracts "--help".
 * For "vyrex onboard --from", extracts "onboard".
 */
export function globalCommandTokens(): Set<string> {
  const tokens = new Set<string>();
  for (const cmd of globalCommands()) {
    // Extract the token after "vyrex "
    const rest = cmd.usage.replace(/^vyrex\s+/, "");
    // First word (handles "tunnel start" → "tunnel", "onboard --from" → "onboard")
    const token = rest.split(/\s+/)[0];
    tokens.add(token);
  }
  return tokens;
}

/**
 * Action tokens for sandbox commands.
 * Replaces the hand-maintained sandboxActions array.
 *
 * For "vyrex <name> connect", extracts "connect".
 * Includes empty string for default connect behavior.
 */
export function sandboxActionTokens(): string[] {
  const seen = new Set<string>();
  const tokens: string[] = [];
  for (const cmd of sandboxCommands()) {
    // Extract action: "vyrex <name> connect" → "connect"
    const rest = cmd.usage.replace(/^vyrex\s+<name>\s*/, "");
    // First word: "snapshot create" → "snapshot", "connect" → "connect"
    const token = rest.split(/\s+/)[0];
    if (!seen.has(token)) {
      seen.add(token);
      tokens.push(token);
    }
  }
  // Include empty string for default connect (no action specified)
  if (!seen.has("")) {
    tokens.push("");
  }
  return tokens;
}
