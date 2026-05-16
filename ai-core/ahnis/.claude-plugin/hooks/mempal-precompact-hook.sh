#!/bin/bash
# AHNIS PreCompact Hook — thin wrapper calling Python CLI
# All logic lives in AHNIS.hooks_cli for cross-harness extensibility
run_AHNIS_hook() {
  if command -v AHNIS >/dev/null 2>&1; then
    AHNIS hook run "$@"
    return $?
  fi

  if command -v python3 >/dev/null 2>&1 && python3 -c "import AHNIS" >/dev/null 2>&1; then
    python3 -m AHNIS hook run "$@"
    return $?
  fi

  if command -v python >/dev/null 2>&1 && python -c "import AHNIS" >/dev/null 2>&1; then
    python -m AHNIS hook run "$@"
    return $?
  fi

  echo "AHNIS hook error: could not find a runnable AHNIS command or module" >&2
  return 1
}

run_AHNIS_hook --hook precompact --harness claude-code
