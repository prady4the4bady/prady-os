// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { describe, it, expect } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

const UNINSTALL_SCRIPT = path.join(import.meta.dirname, "..", "uninstall.sh");

function createFakeNpmEnv(tmp: string): Record<string, string | undefined> {
  const fakeBin = path.join(tmp, "bin");
  const npmPath = path.join(fakeBin, "npm");
  fs.mkdirSync(fakeBin, { recursive: true });
  fs.writeFileSync(npmPath, "#!/usr/bin/env bash\nexit 0\n", { mode: 0o755 });
  return {
    ...process.env,
    HOME: tmp,
    PATH: `${fakeBin}:${process.env.PATH || "/usr/bin:/bin"}`,
  };
}

describe("uninstall CLI flags", () => {
  it("--help exits 0 and shows usage", () => {
    const result = spawnSync("bash", [UNINSTALL_SCRIPT, "--help"], {
      cwd: path.join(import.meta.dirname, ".."),
      encoding: "utf-8",
    });

    expect(result.status).toBe(0);
    const output = `${result.stdout}${result.stderr}`;
    expect(output).toMatch(/Vyrex Uninstaller/);
    expect(output).toMatch(/--yes/);
    expect(output).toMatch(/--keep-openshell/);
    expect(output).toMatch(/--delete-models/);
  });

  it("--yes skips the confirmation prompt and completes successfully", () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "vyrex-uninstall-yes-"));
    const fakeBin = path.join(tmp, "bin");
    fs.mkdirSync(fakeBin);

    try {
      for (const cmd of ["npm", "openshell", "docker", "ollama", "pgrep"]) {
        fs.writeFileSync(path.join(fakeBin, cmd), "#!/usr/bin/env bash\nexit 0\n", {
          mode: 0o755,
        });
      }

      const result = spawnSync("bash", [UNINSTALL_SCRIPT, "--yes"], {
        cwd: path.join(import.meta.dirname, ".."),
        encoding: "utf-8",
        env: {
          ...process.env,
          HOME: tmp,
          PATH: `${fakeBin}:/usr/bin:/bin`,
          SCRIPT_DIR: path.join(import.meta.dirname, ".."),
          // Keep helper-service glob cleanup isolated from concurrently running tests.
          TMPDIR: tmp,
        },
      });

      expect(result.status).toBe(0);
      const output = `${result.stdout}${result.stderr}`;
      expect(output).toMatch(/Vyrex/);
      expect(output).toMatch(/Claws retracted/);
    } finally {
      fs.rmSync(tmp, { recursive: true, force: true });
    }
  }, 60_000);
});

describe("uninstall helpers", () => {
  it("returns the expected gateway volume candidate", () => {
    const result = spawnSync(
      "bash",
      ["-c", `source "${UNINSTALL_SCRIPT}"; gateway_volume_candidates vyrex`],
      {
        cwd: path.join(import.meta.dirname, ".."),
        encoding: "utf-8",
      },
    );

    expect(result.status).toBe(0);
    expect(result.stdout.trim()).toBe("openshell-cluster-vyrex");
  });

  it("removes the user-local vyrex shim", () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "vyrex-uninstall-shim-"));
    const shimDir = path.join(tmp, ".local", "bin");
    const shimPath = path.join(shimDir, "vyrex");
    const targetPath = path.join(tmp, "prefix", "bin", "vyrex");

    fs.mkdirSync(shimDir, { recursive: true });
    fs.mkdirSync(path.dirname(targetPath), { recursive: true });
    fs.writeFileSync(targetPath, "#!/usr/bin/env bash\n", { mode: 0o755 });
    fs.symlinkSync(targetPath, shimPath);

    const result = spawnSync("bash", ["-c", `source "${UNINSTALL_SCRIPT}"; remove_vyrex_cli`], {
      cwd: path.join(import.meta.dirname, ".."),
      encoding: "utf-8",
      env: createFakeNpmEnv(tmp),
    });

    expect(result.status).toBe(0);
    expect(fs.existsSync(shimPath)).toBe(false);
  }, 60_000);

  it("preserves a user-managed vyrex file in the shim directory", () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "vyrex-uninstall-preserve-"));
    const shimDir = path.join(tmp, ".local", "bin");
    const shimPath = path.join(shimDir, "vyrex");

    fs.mkdirSync(shimDir, { recursive: true });
    fs.writeFileSync(shimPath, "#!/usr/bin/env bash\n", { mode: 0o755 });

    const result = spawnSync("bash", ["-c", `source "${UNINSTALL_SCRIPT}"; remove_vyrex_cli`], {
      cwd: path.join(import.meta.dirname, ".."),
      encoding: "utf-8",
      env: createFakeNpmEnv(tmp),
    });

    expect(result.status).toBe(0);
    expect(fs.existsSync(shimPath)).toBe(true);
    expect(`${result.stdout}${result.stderr}`).toMatch(/not an installer-managed shim/);
  }, 60_000);

  it("removes an installer-managed vyrex wrapper file in the shim directory", () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "vyrex-uninstall-wrapper-"));
    const shimDir = path.join(tmp, ".local", "bin");
    const shimPath = path.join(shimDir, "vyrex");

    fs.mkdirSync(shimDir, { recursive: true });
    fs.writeFileSync(
      shimPath,
      [
        "#!/usr/bin/env bash",
        'export PATH="/tmp/node-bin:$PATH"',
        'exec "/tmp/prefix/bin/vyrex" "$@"',
        "",
      ].join("\n"),
      { mode: 0o755 },
    );

    const result = spawnSync("bash", ["-c", `source "${UNINSTALL_SCRIPT}"; remove_vyrex_cli`], {
      cwd: path.join(import.meta.dirname, ".."),
      encoding: "utf-8",
      env: createFakeNpmEnv(tmp),
    });

    expect(result.status).toBe(0);
    expect(fs.existsSync(shimPath)).toBe(false);
  }, 60_000);

  it("removes a dev-install shim written by scripts/npm-link-or-shim.sh", () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "vyrex-uninstall-dev-shim-"));
    const shimDir = path.join(tmp, ".local", "bin");
    const shimPath = path.join(shimDir, "vyrex");

    fs.mkdirSync(shimDir, { recursive: true });
    fs.writeFileSync(
      shimPath,
      [
        "#!/usr/bin/env bash",
        "# Vyrex dev-shim - managed by scripts/npm-link-or-shim.sh",
        'export PATH="/tmp/node-bin:$PATH"',
        'exec "/tmp/checkout/bin/vyrex.js" "$@"',
        "",
      ].join("\n"),
      { mode: 0o755 },
    );

    const result = spawnSync("bash", ["-c", `source "${UNINSTALL_SCRIPT}"; remove_vyrex_cli`], {
      cwd: path.join(import.meta.dirname, ".."),
      encoding: "utf-8",
      env: createFakeNpmEnv(tmp),
    });

    expect(result.status).toBe(0);
    expect(fs.existsSync(shimPath)).toBe(false);
  }, 60_000);

  it("preserves a wrapper-like shim when extra content is appended", () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "vyrex-uninstall-wrapper-extra-"));
    const shimDir = path.join(tmp, ".local", "bin");
    const shimPath = path.join(shimDir, "vyrex");

    fs.mkdirSync(shimDir, { recursive: true });
    fs.writeFileSync(
      shimPath,
      [
        "#!/usr/bin/env bash",
        'export PATH="/tmp/node-bin:$PATH"',
        'exec "/tmp/prefix/bin/vyrex" "$@"',
        "echo user-extra",
        "",
      ].join("\n"),
      { mode: 0o755 },
    );

    const result = spawnSync("bash", ["-c", `source "${UNINSTALL_SCRIPT}"; remove_vyrex_cli`], {
      cwd: path.join(import.meta.dirname, ".."),
      encoding: "utf-8",
      env: createFakeNpmEnv(tmp),
    });

    expect(result.status).toBe(0);
    expect(fs.existsSync(shimPath)).toBe(true);
    expect(`${result.stdout}${result.stderr}`).toMatch(/not an installer-managed shim/);
  }, 60_000);

  it("removes the onboard session file as part of Vyrex state cleanup", () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "vyrex-uninstall-session-"));
    const stateDir = path.join(tmp, ".vyrex");
    const sessionPath = path.join(stateDir, "onboard-session.json");

    fs.mkdirSync(stateDir, { recursive: true });
    fs.writeFileSync(sessionPath, JSON.stringify({ status: "complete" }));

    const result = spawnSync(
      "bash",
      ["-c", `source "${UNINSTALL_SCRIPT}"; remove_vyrex_state`],
      {
        cwd: path.join(import.meta.dirname, ".."),
        encoding: "utf-8",
        env: { ...process.env, HOME: tmp },
      },
    );

    expect(result.status).toBe(0);
    expect(fs.existsSync(sessionPath)).toBe(false);
    expect(fs.existsSync(stateDir)).toBe(false);
  }, 60_000);
});
