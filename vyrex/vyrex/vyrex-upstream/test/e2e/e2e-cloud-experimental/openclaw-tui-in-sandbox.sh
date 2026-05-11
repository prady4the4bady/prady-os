#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# shellcheck disable=SC2016
# expect(1) Tcl: $ and {...} are Tcl, not bash expansion
#
# OpenClaw TUI flow in one command (local / interactive).
#
# Automated CI-style smoke (finite expect, no `interact`) runs as Phase 5e inside:
#   test/e2e/test-e2e-cloud-experimental.sh
#
#   default: use `expect` to run `vyrex <sandbox> connect`, then send `openclaw tui`
#   manual:  pass --manual to only run `vyrex <sandbox> connect`
#
# Usage:
#   bash test/e2e/e2e-cloud-experimental/openclaw-tui-in-sandbox.sh
#   bash test/e2e/e2e-cloud-experimental/openclaw-tui-in-sandbox.sh my-sandbox
#   bash test/e2e/e2e-cloud-experimental/openclaw-tui-in-sandbox.sh --manual
#
# Optional env:
#   OPENCLAW_TUI_AUTO_MESSAGE   default: 你好
#   OPENCLAW_TUI_SEND_DELAY_SEC default: 3

set -euo pipefail

MANUAL_MODE=0
CLI_SANDBOX_NAME=""
for arg in "$@"; do
  case "$arg" in
    --manual) MANUAL_MODE=1 ;;
    *)
      if [ -z "$CLI_SANDBOX_NAME" ]; then
        CLI_SANDBOX_NAME="$arg"
      else
        echo "ERROR: unexpected extra argument: $arg" >&2
        exit 1
      fi
      ;;
  esac
done
SANDBOX_NAME="${CLI_SANDBOX_NAME:-${SANDBOX_NAME:-${VYREX_SANDBOX_NAME:-e2e-cloud-experimental}}}"

if ! command -v vyrex >/dev/null 2>&1; then
  echo "ERROR: vyrex not on PATH." >&2
  exit 1
fi

if [ "$MANUAL_MODE" -eq 1 ]; then
  exec vyrex "$SANDBOX_NAME" connect
fi

printf '%s\n' \
  "Connecting to sandbox '${SANDBOX_NAME}' and launching openclaw tui..." \
  "After TUI opens, send your message (e.g. 你好)." \
  ""

if command -v expect >/dev/null 2>&1; then
  AUTO_MESSAGE="${OPENCLAW_TUI_AUTO_MESSAGE:-你好}"
  SEND_DELAY_SEC="${OPENCLAW_TUI_SEND_DELAY_SEC:-3}"
  exec env \
    VYREX_TUI_SANDBOX_NAME="$SANDBOX_NAME" \
    OPENCLAW_TUI_AUTO_MESSAGE="$AUTO_MESSAGE" \
    OPENCLAW_TUI_SEND_DELAY_SEC="$SEND_DELAY_SEC" \
    expect -c '
    set timeout -1
    set sandbox $env(VYREX_TUI_SANDBOX_NAME)
    set auto_msg $env(OPENCLAW_TUI_AUTO_MESSAGE)
    set send_delay $env(OPENCLAW_TUI_SEND_DELAY_SEC)
    spawn vyrex $sandbox connect
    expect {
      -re {[$#>] $} {
        send "openclaw tui\r"
        sleep $send_delay
        send -- "$auto_msg\r"
        interact
      }
      timeout { puts "Timed out waiting for sandbox shell prompt."; exit 1 }
      eof { exit 1 }
    }
  '
fi

echo "WARN: expect not found; falling back to manual connect." >&2
echo "After entering sandbox, run: openclaw tui" >&2
exec vyrex "$SANDBOX_NAME" connect
