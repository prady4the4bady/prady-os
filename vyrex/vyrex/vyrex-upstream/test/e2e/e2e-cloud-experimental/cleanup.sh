#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Shared teardown for e2e-cloud-experimental (extracted from test-e2e-cloud-experimental.sh Phase 0 + Phase 6).
#
# Destroys vyrex sandbox, OpenShell sandbox, port 18789 forward, and vyrex gateway.
#
# Usage:
#   SANDBOX_NAME=my-sbx bash test/e2e/e2e-cloud-experimental/cleanup.sh
#   SANDBOX_NAME=my-sbx bash test/e2e/e2e-cloud-experimental/cleanup.sh --verify
#
# Environment:
#   SANDBOX_NAME or VYREX_SANDBOX_NAME — default: e2e-cloud-experimental
#
# Modes:
#   (default)  — destroy only (best-effort; always exits 0)
#   --verify   — destroy then assert sandbox is gone from openshell get + vyrex list (exits 1 on failure)

set -uo pipefail

pass() { printf '\033[32m  PASS: %s\033[0m\n' "$1"; }
fail() { printf '\033[31m  FAIL: %s\033[0m\n' "$1"; }
skip() { printf '\033[33m  SKIP: %s\033[0m\n' "$1"; }
info() { printf '\033[1;34m  [info]\033[0m %s\n' "$1"; }

SANDBOX_NAME="${VYREX_SANDBOX_NAME:-${SANDBOX_NAME:-e2e-cloud-experimental}}"
VERIFY=0
if [ "${1:-}" = "--verify" ]; then
  VERIFY=1
fi

info "e2e-cloud-experimental cleanup: sandbox='${SANDBOX_NAME}' (verify=${VERIFY})"

if command -v vyrex >/dev/null 2>&1; then
  vyrex "$SANDBOX_NAME" destroy --yes 2>/dev/null || true
fi
if command -v openshell >/dev/null 2>&1; then
  openshell sandbox delete "$SANDBOX_NAME" 2>/dev/null || true
  openshell forward stop 18789 2>/dev/null || true
  openshell gateway destroy -g vyrex 2>/dev/null || true
fi

if [ "$VERIFY" != "1" ]; then
  pass "Cleanup destroy complete (no --verify)"
  exit 0
fi

# ── Post-teardown checks (Phase 6 parity) ──
if command -v openshell >/dev/null 2>&1; then
  if openshell sandbox get "$SANDBOX_NAME" >/dev/null 2>&1; then
    fail "openshell sandbox get '${SANDBOX_NAME}' still succeeds after cleanup"
    exit 1
  fi
  pass "openshell: sandbox '${SANDBOX_NAME}' no longer visible to sandbox get"
else
  skip "openshell not on PATH — skipped sandbox get check after cleanup"
fi

if command -v vyrex >/dev/null 2>&1; then
  set +e
  list_out=$(vyrex list 2>&1)
  list_rc=$?
  set -uo pipefail
  if [ "$list_rc" -eq 0 ]; then
    if echo "$list_out" | grep -Fq "    ${SANDBOX_NAME}"; then
      fail "vyrex list still lists '${SANDBOX_NAME}' after destroy"
      exit 1
    fi
    pass "vyrex list: '${SANDBOX_NAME}' removed from registry"
  else
    skip "vyrex list failed after cleanup — could not verify registry (exit $list_rc)"
  fi
else
  skip "vyrex not on PATH — skipped list check after cleanup"
fi

pass "Cleanup + verify complete"
exit 0
