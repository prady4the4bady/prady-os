// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Regression guard for issue #2376:
 *   Lumyn Agent crashes on every keypress because LUMYN_HOME is unset
 *   in interactive sandbox shells, so proxy settings and Lumyn runtime
 *   configuration from /tmp/vyrex-proxy-env.sh are missing.
 *
 * Root cause:
 *   The OpenClaw base image (Dockerfile.base) pre-creates /sandbox/.bashrc
 *   and /sandbox/.profile that source /tmp/vyrex-proxy-env.sh — the file
 *   the entrypoint writes with LUMYN_HOME (and proxy vars) at runtime.
 *   The Lumyn base image (agents/lumyn/Dockerfile.base) was missing the
 *   equivalent block, so the proxy-env file existed but was never sourced.
 *
 *   The regression slipped in via #2297 which moved the proxy/LUMYN_HOME
 *   exports out of an inline .bashrc append into the standalone proxy-env
 *   file — without realising the Lumyn base image had no .bashrc to source it.
 */

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { describe, expect, it } from "vitest";

function runRcFile(
  rcFileName: ".bashrc" | ".profile",
  proxyEnvContents?: string,
  command = `printf '%s' "\${LUMYN_HOME:-}"`,
): string {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "nc-2376-"));
  try {
    const childEnv = { ...process.env };
    delete childEnv.LUMYN_HOME;

    const proxyEnv = path.join(tmp, "vyrex-proxy-env.sh");
    const rcFile = path.join(tmp, rcFileName);

    if (proxyEnvContents !== undefined) {
      fs.writeFileSync(proxyEnv, proxyEnvContents);
    }
    fs.writeFileSync(
      rcFile,
      [
        `[ -f ${proxyEnv} ] && . ${proxyEnv}`,
        'export PATH="/usr/local/bin:/opt/lumyn/.venv/bin:${PATH}"',
        "",
      ].join("\n"),
    );

    return execFileSync("bash", ["-c", `. "${rcFile}"; ${command}`], {
      encoding: "utf-8",
      env: childEnv,
    });
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

describe("Issue #2376: Lumyn rc files source LUMYN_HOME from proxy-env", () => {
  for (const rcFileName of [".bashrc", ".profile"] as const) {
    it(`${rcFileName} exports LUMYN_HOME when proxy-env exists`, () => {
      const out = runRcFile(rcFileName, "export LUMYN_HOME=/sandbox/.lumyn\n");
      expect(out).toBe("/sandbox/.lumyn");
    });

    it(`${rcFileName} prepends Lumyn command directories to PATH`, () => {
      const out = runRcFile(rcFileName, undefined, `printf '%s' "$PATH"`);
      expect(out.split(":").slice(0, 2)).toEqual(["/usr/local/bin", "/opt/lumyn/.venv/bin"]);
    });
  }

  it("rc sourcing is a no-op when proxy-env is absent", () => {
    const out = runRcFile(".bashrc");
    expect(out).toBe("");
  });
});
