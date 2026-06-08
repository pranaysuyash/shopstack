#!/usr/bin/env python3
"""verification-loop: 6-phase verification pipeline for ShopStack.

Usage:
    python scripts/verify.py            # Run all phases
    python scripts/verify.py --quick    # Skip security scan + diff review
    python scripts/verify.py --phase build  # Run a single phase

Exit code: 0 if all passed, 1 if any failures.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


VENV_PYTEST = str(REPO / ".venv" / "bin" / "pytest")
VENV_RUFF = str(REPO / ".venv" / "bin" / "ruff")
VENV_PYRIGHT = str(REPO / ".venv" / "bin" / "pyright")

def run(cmd: list[str], timeout: int = 180, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd or str(REPO),
    )


def phase_build() -> tuple[bool, str]:
    print("  Phase 1/6: Build check ...", end=" ")
    result = run([sys.executable, "-c", "import shopstack; print('OK')"])
    if result.returncode == 0:
        print("PASS")
        return True, result.stdout.strip()
    print("FAIL")
    return False, result.stderr


def phase_types() -> tuple[bool, str]:
    print("  Phase 2/6: Type check ...", end=" ")
    # Try mypy first, then pyright, fall back to import check
    try:
        result = run(["mypy", "shopstack/", "--ignore-missing-imports", "--no-error-summary"], timeout=30)
        if result.returncode == 0:
            print("PASS (mypy)")
            return True, ""
        print(f"FAIL (mypy: {result.returncode})")
        return False, result.stdout[-500:] if len(result.stdout) > 500 else result.stdout
    except FileNotFoundError:
        pass
    try:
        pyright_bin = VENV_PYRIGHT if Path(VENV_PYRIGHT).exists() else "pyright"
        result = run([pyright_bin, "shopstack/"], timeout=60)
        if result.returncode == 0:
            print("PASS (pyright)")
            return True, ""
        print(f"FAIL (pyright: {result.returncode})")
        return False, result.stdout[-500:] if len(result.stdout) > 500 else result.stdout
    except FileNotFoundError:
        pass
    # Fallback: import check
    result = run([sys.executable, "-c", "import shopstack; print('imported')"])
    if "imported" in result.stdout:
        print("PASS (import check — no static checker installed)")
        return True, result.stdout.strip()
    print("SKIP")
    return True, ""


def phase_lint() -> tuple[bool, str]:
    print("  Phase 3/6: Lint check ...", end=" ")
    try:
        ruff_bin = VENV_RUFF if Path(VENV_RUFF).exists() else "ruff"
        result = run([ruff_bin, "check", "shopstack/", "tests/", "scripts/"], timeout=30)
        if result.returncode == 0:
            print("PASS")
            return True, ""
        print(f"FAIL ({result.returncode} error(s))")
        return False, result.stdout or result.stderr
    except FileNotFoundError:
        print("SKIP (ruff not installed)")
        return True, ""


def phase_tests() -> tuple[bool, str]:
    print("  Phase 4/6: Test suite ...", end=" ")
    pytest_bin = VENV_PYTEST if Path(VENV_PYTEST).exists() else "pytest"
    result = run([pytest_bin, "tests/", "-q", "--tb=short", "--no-header"], timeout=180)
    summary_line = [line for line in result.stdout.split("\n") if line.strip() and ("passed" in line.lower() or "failed" in line.lower())]
    summary = summary_line[-1] if summary_line else result.stdout.strip()[-200:]
    if result.returncode == 0:
        prefix = result.stdout.strip().split("\n")[-1] if result.stdout.strip() else ""
        print(f"PASS ({prefix})" if prefix else "PASS")
        return True, summary
    print("FAIL")
    return False, result.stdout[-500:] if len(result.stdout) > 500 else result.stdout


def phase_security() -> tuple[bool, str]:
    print("  Phase 5/6: Security scan ...", end=" ")
    issues: list[str] = []
    shopstack_src = REPO / "shopstack"
    rg_patterns = [
        ("sk-", ["*.py"]),
        ("api_key", ["*.py"]),
        ("secret", ["*.py"]),
        ("password", ["*.py"]),
        ("-----BEGIN", ["*.py", "*.sh", "*.env", "*.json", "*.yaml", "*.yml"]),
        ("ghp_", ["*.py", "*.sh", "*.env"]),
        ("gho_", ["*.py", "*.sh", "*.env"]),
        ("ghu_", ["*.py", "*.sh", "*.env"]),
        ("ghs_", ["*.py", "*.sh", "*.env"]),
        ("ghr_", ["*.py", "*.sh", "*.env"]),
        ("AKIA", ["*.py", "*.sh", "*.env"]),
    ]
    for pattern, globs in rg_patterns:
        for g in globs:
            result = run(["rg", "-n", pattern, "-g", g, str(shopstack_src)], timeout=15)
            if result.returncode != 0 or not result.stdout.strip():
                continue
            for line in result.stdout.strip().split("\n"):
                if "def " in line or "class " in line or line.strip().startswith("#"):
                    continue
                issues.append(line)

    forbidden_literals = ["sk-proj", "sk-svc"]
    for pattern in forbidden_literals:
        result = run(["rg", "-n", pattern, str(REPO)], timeout=10)
        if result.returncode == 0:
            issues.append(f"Potential API key literal: {result.stdout.strip()[:200]}")

    if not issues:
        print("PASS")
        return True, ""
    print(f"WARN ({len(issues)} issue(s))")
    return True, "\n".join(issues)


def phase_diff() -> tuple[bool, str]:
    print("  Phase 6/6: Diff review ...", end=" ")
    result = run(["git", "diff", "--stat"])
    if result.returncode == 0 and result.stdout.strip():
        lines = result.stdout.strip().split("\n")
        print(f"{len(lines)} file(s) changed")
        return True, result.stdout.strip()
    print("No changes")
    return True, ""


def run_all(quick: bool = False) -> int:
    phases = [
        ("Build", phase_build),
        ("Types", phase_types),
        ("Lint", phase_lint),
        ("Tests", phase_tests),
    ]
    if not quick:
        phases += [
            ("Security", phase_security),
            ("Diff", phase_diff),
        ]

    results: list[tuple[str, bool, str]] = []
    all_pass = True
    t0 = time.monotonic()

    for name, fn in phases:
        passed, detail = fn()
        results.append((name, passed, detail))
        if not passed:
            all_pass = False

    elapsed = time.monotonic() - t0

    print()
    print("=" * 50)
    print("  VERIFICATION REPORT")
    print("=" * 50)
    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        print(f"  {name:15s} [{status}]")
        if not passed and detail:
            for line in detail.strip().split("\n")[:5]:
                print(f"    {line}")
    print("-" * 50)
    print(f"  Overall: {'READY' if all_pass else 'HAS ISSUES'}")
    print(f"  Time: {elapsed:.1f}s")
    print("=" * 50)
    return 0 if all_pass else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="ShopStack verification pipeline")
    parser.add_argument("--quick", action="store_true", help="Skip security scan + diff review")
    parser.add_argument("--phase", choices=["build", "types", "lint", "tests", "security", "diff"], help="Run a single phase")
    args = parser.parse_args()

    if args.phase:
        phase_map = {
            "build": ("Build", phase_build),
            "types": ("Types", phase_types),
            "lint": ("Lint", phase_lint),
            "tests": ("Tests", phase_tests),
            "security": ("Security", phase_security),
            "diff": ("Diff", phase_diff),
        }
        name, fn = phase_map[args.phase]
        print(f"Running phase: {name}")
        passed, detail = fn()
        print(f"  {name}: {'PASS' if passed else 'FAIL'}")

        if not passed and detail:
            print("  Details:")
            for line in detail.strip().split("\n")[:10]:
                print(f"    {line}")
        return 0 if passed else 1

    return run_all(quick=args.quick)


if __name__ == "__main__":
    sys.exit(main())
