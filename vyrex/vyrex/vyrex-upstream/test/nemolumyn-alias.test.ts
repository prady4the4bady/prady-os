// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { describe, it, expect } from "vitest";
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

import { execTimeout } from "./helpers/timeouts";

const LUMYN_CLI = path.join(import.meta.dirname, "..", "bin", "vyrex-lumyn.js");
const VYREX_CLI = path.join(import.meta.dirname, "..", "bin", "vyrex.js");

function runLumyn(
  args: string,
  env: Record<string, string | undefined> = {},
): { code: number; out: string } {
  try {
    const out = execSync(`node "${LUMYN_CLI}" ${args}`, {
      encoding: "utf-8",
      timeout: execTimeout(),
      env: {
        ...process.env,
        HOME: "/tmp/vyrex-lumyn-test-" + Date.now(),
        VYREX_HEALTH_POLL_COUNT: "1",
        VYREX_HEALTH_POLL_INTERVAL: "0",
        ...env,
      },
    });
    return { code: 0, out };
  } catch (err: unknown) {
    const e = err as { status?: number; stdout?: string | Buffer; stderr?: string | Buffer };
    const stdout = typeof e.stdout === "string" ? e.stdout : (e.stdout?.toString("utf8") ?? "");
    const stderr = typeof e.stderr === "string" ? e.stderr : (e.stderr?.toString("utf8") ?? "");
    return { code: e.status ?? 1, out: stdout + stderr };
  }
}

function runVyrex(
  args: string,
  env: Record<string, string | undefined> = {},
): { code: number; out: string } {
  try {
    const out = execSync(`node "${VYREX_CLI}" ${args}`, {
      encoding: "utf-8",
      timeout: execTimeout(),
      env: {
        ...process.env,
        HOME: "/tmp/vyrex-lumyn-test-" + Date.now(),
        VYREX_AGENT: undefined,
        VYREX_HEALTH_POLL_COUNT: "1",
        VYREX_HEALTH_POLL_INTERVAL: "0",
        ...env,
      },
    });
    return { code: 0, out };
  } catch (err: unknown) {
    const e = err as { status?: number; stdout?: string | Buffer; stderr?: string | Buffer };
    const stdout = typeof e.stdout === "string" ? e.stdout : (e.stdout?.toString("utf8") ?? "");
    const stderr = typeof e.stderr === "string" ? e.stderr : (e.stderr?.toString("utf8") ?? "");
    return { code: e.status ?? 1, out: stdout + stderr };
  }
}

describe("vyrex-lumyn alias", () => {
  it("bin/vyrex-lumyn.js exists and is executable", () => {
    expect(fs.existsSync(LUMYN_CLI)).toBe(true);
    const stat = fs.statSync(LUMYN_CLI);
    // Owner execute bit
    expect(stat.mode & 0o100).not.toBe(0);
  });

  it("--version outputs vyrex-lumyn branding", () => {
    const { code, out } = runLumyn("--version");
    expect(code).toBe(0);
    expect(out).toMatch(/^vyrex-lumyn v[\d.]+/);
  });

  it("vyrex --version does not contain vyrex-lumyn", () => {
    const { code, out } = runVyrex("--version");
    expect(code).toBe(0);
    expect(out).toMatch(/^vyrex v[\d.]+/);
    expect(out).not.toContain("vyrex-lumyn");
  });

  it("help output shows VyrexLumyn header", () => {
    const { code, out } = runLumyn("--help");
    expect(code).toBe(0);
    expect(out).toContain("VyrexLumyn");
  });

  it("VYREX_AGENT is set to lumyn via the launcher", () => {
    // The launcher sets the env var before requiring dist/vyrex.
    // We verify indirectly: --version shows vyrex-lumyn branding which
    // requires both VYREX_AGENT=lumyn AND argv containing vyrex-lumyn.
    const { code, out } = runLumyn("--version");
    expect(code).toBe(0);
    expect(out).toContain("vyrex-lumyn");
  });

  it("vyrex onboard --agent lumyn uses Lumyn branding after agent resolution", () => {
    const { code, out } = runVyrex(
      "onboard --agent lumyn --resume --non-interactive --yes-i-accept-third-party-software",
    );
    expect(code).toBe(1);
    expect(out).toContain("vyrex-lumyn onboard");
  });
});
