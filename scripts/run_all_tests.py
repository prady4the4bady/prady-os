#!/usr/bin/env python3
"""Run all relevant Prady OS test suites from repo root.

Usage:
    python scripts/run_all_tests.py              # all suites
    python scripts/run_all_tests.py --fail-fast   # stop on first failure

Each suite runs as a subprocess from the repo root so that service-level
conftest files resolve their own `app.main` without namespace collisions.
"""
from __future__ import annotations

import subprocess
import sys
import time

SUITES: list[tuple[str, list[str]]] = [
    # Only target our production test files, not the imported ouroboros/mempalace full suites
    ("ai-core/neila/tests/test_neila.py", ["python", "-m", "pytest", "-W", "error::DeprecationWarning", "-q"]),
    ("ai-core/ahnis/tests/test_ahnis.py", ["python", "-m", "pytest", "-W", "error::DeprecationWarning", "-q"]),
    ("platform/agent-runtime/tests/", ["python", "-m", "pytest", "-W", "error::DeprecationWarning", "-q"]),
    ("platform/tests/test_feature_claims.py", ["python", "-m", "pytest", "-W", "error::DeprecationWarning", "-q"]),
]


def _fmt_duration(secs: float) -> str:
    if secs < 60:
        return f"{secs:.1f}s"
    return f"{secs / 60:.1f}m ({secs:.0f}s)"


def run() -> int:
    fail_fast = "--fail-fast" in sys.argv
    results: list[dict[str, object]] = []
    any_failed = False
    overall_start = time.perf_counter()

    for label, cmd in SUITES:
        start = time.perf_counter()
        header = f"  {label}  "
        print(f"\n{'=' * 60}")
        print(f" RUNNING: {label}")
        print(f"{'=' * 60}")
        sys.stdout.flush()
        result = subprocess.run(cmd + [label], capture_output=False)
        elapsed = time.perf_counter() - start
        passed = result.returncode == 0
        status = "PASS" if passed else "FAIL"
        results.append({"label": label, "status": status, "returncode": result.returncode, "duration": elapsed})
        if not passed:
            any_failed = True
            if fail_fast:
                print(f"\nFAILED: {label} — aborting (--fail-fast)")
                break

    overall_elapsed = time.perf_counter() - overall_start

    # Summary table
    print(f"\n{'=' * 60}")
    print(f" {'SUMMARY':^56}")
    print(f"{'=' * 60}")
    print(f" {'Suite':<50} {'Result':>6} {'Time':>8}")
    print(f" {'-'*48:<50} {'-'*4:>6} {'-'*6:>8}")
    for r in results:
        dur_str = _fmt_duration(r["duration"])  # type: ignore[arg-type]
        print(f" {r['label']:<50} {r['status']:>6} {dur_str:>8}")
    print(f" {'-'*48:<50} {'-'*4:>6} {'-'*6:>8}")
    total = len(results)
    passed_count = sum(1 for r in results if r["status"] == "PASS")
    failed_count = total - passed_count
    print(f" {'Total':<50} {f'{passed_count}/{total}':>6} {_fmt_duration(overall_elapsed):>8}")
    if any_failed:
        print(f"\nFAILED: {failed_count} suite(s) failed — exit code 1")
    else:
        print(f"\nAll {total} suite(s) passed.")
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(run())
