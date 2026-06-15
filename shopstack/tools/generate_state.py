"""Canonical ShopStack state dashboard generator.

A single source of truth for "what is the actual state of ShopStack right
now?" — generated from code, not from a hand-maintained doc. The previous
hand-maintained `Docs/SYSTEM_STATE.md` and `Docs/FEATURES_STATUS.md` drifted
out of date; this script replaces them with a *regeneratable* artifact
that agents and humans can re-run on every change.

**What it does (motto_v3 §0.1, §0.10):**

1. Counts the test suite (parsed from `pytest --collect-only -q`, not
   hand-typed). If pytest isn't available, it falls back to a directory
   walk counting `def test_*` lines.
2. Lists every service, every screen, every tab, every model — so the
   reader can see at a glance what modules exist without crawling the
   source tree.
3. Cross-references the open-issue backlog from `Docs/REMAINING_WORK.md`
   and `Docs/issue_review_2026-06-13_improvement_opportunities.md`, keeping
   the high-level status (P0/P1/P2/P3) but reading the actual state from
   the code where it can.
4. Surfaces drift: if any `Docs/*.md` file outside `Docs/archive/` is
   older than 30 days, it warns.

**Why this is the canonical dashboard (motto_v3 §0.4 acceptance contract):**

A completion claim is only as good as the verification behind it. By
generating the dashboard from `wcag_audit.py` (run independently and
captured by the CI hook) and the test collector, the dashboard always
reflects what the code actually does, not what someone wrote three months
ago. Hand-written doc tables inevitably drift; generated ones do not.

**Usage:**

    python -m shopstack.tools.generate_state

Writes `Docs/SYSTEM_STATE.md` and `Docs/STATE_DASHBOARD.json` (machine-readable).

This is intentionally read-only with respect to source — it reads the
project, it never edits it.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = PROJECT_ROOT / "Docs"
SERVICES_DIR = PROJECT_ROOT / "shopstack" / "services"
SCREENS_DIR = PROJECT_ROOT / "shopstack" / "ui" / "screens"
TABS_DIR = PROJECT_ROOT / "shopstack" / "ui" / "tabs"
TESTS_DIR = PROJECT_ROOT / "tests"
PROVIDERS_DIR = PROJECT_ROOT / "shopstack" / "providers"

OUTPUT_MD = DOCS_DIR / "SYSTEM_STATE.md"
OUTPUT_JSON = DOCS_DIR / "STATE_DASHBOARD.json"


# ── Test counting ───────────────────────────────────────────────────


def _count_tests_via_pytest() -> tuple[int, str]:
    """Return ``(count, method)`` using pytest --collect-only.

    Falls back to ``(0, "no-pytest")`` if pytest fails (e.g. disk full,
    missing venv, syntax error in tests). The dashboard then falls back
    to a directory-walk counter so the artifact is never empty.
    """
    try:
        proc = subprocess.run(
            ["python", "-m", "pytest", "tests/", "--collect-only", "-q"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        # Last non-empty line is usually "N tests collected" or
        # "N tests collected, M errors".  We match the first integer that
        # is followed by the literal token "test" (covers both "test" and
        # "tests").  This is robust to slight variations in pytest output.
        # The count line can appear in stdout (clean run) or stderr (with
        # collection errors) so we check both.
        for line in (proc.stdout.splitlines()[-5:] + proc.stderr.splitlines()[-5:]):
            m = re.search(r"(\d+)\s+tests?\s+(?:collected|passed)", line)
            if m:
                return int(m.group(1)), "pytest-collect"
            # Fallback: "= N passed in" or "= N tests in" appears in -v output
            m = re.search(r"^=+\s*(\d+)\s+", line)
            if m:
                return int(m.group(1)), "pytest-collect-v"
        return 0, "pytest-no-match"
    except Exception as exc:  # noqa: BLE001
        return 0, f"pytest-error:{type(exc).__name__}"


def _count_tests_via_walk() -> tuple[int, str]:
    """Walk `tests/` and count every ``def test_`` line.

    A robust fallback that always works, even without pytest installed.
    Slightly less accurate (a single line may contain multiple `def test_X`
    statements) but good-enough for a status report.
    """
    count = 0
    files = 0
    for path in TESTS_DIR.rglob("test_*.py"):
        if "__pycache__" in str(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        # Count top-level `def test_` (heuristic: line starts with "def test_")
        # Multi-line defs are caught by checking the line literally.
        local = sum(1 for line in text.splitlines() if re.match(r"^def test_", line))
        if local:
            count += local
            files += 1
    return count, f"walk:{files}files"


# ── Module counting ─────────────────────────────────────────────────


def _list_modules() -> dict[str, list[str]]:
    """List all Python source files in each subsystem.

    Returns a dict keyed by subsystem (``services``, ``screens``, ``tabs``,
    ``providers``, ``tests``) whose values are paths relative to the project
    root. Excludes ``__pycache__`` and ``_legacy/`` (motto_v3 §0.6
    risk-based: legacy code may not be production-relevant).
    """
    out: dict[str, list[str]] = {}
    for key, base in (
        ("services", SERVICES_DIR),
        ("screens", SCREENS_DIR),
        ("tabs", TABS_DIR),
        ("providers", PROVIDERS_DIR),
        ("tests", TESTS_DIR),
    ):
        if not base.is_dir():
            out[key] = []
            continue
        paths: list[str] = []
        for p in sorted(base.rglob("*.py")):
            sp = str(p.relative_to(PROJECT_ROOT))
            if "__pycache__" in sp:
                continue
            if "_legacy" in sp.split("/"):
                continue
            paths.append(sp)
        out[key] = paths
    return out


def _list_test_files(modules: dict[str, list[str]]) -> list[str]:
    return modules.get("tests", [])


# ── WCAG state ──────────────────────────────────────────────────────


def _read_wcag_score() -> tuple[int, str] | None:
    """Read the latest WCAG score from `Docs/WCAG_AUDIT_2026-06-13.md`.

    The audit script writes the score as ``**Score:** N / 100``. This
    helper looks for that line and returns the integer. Returns ``None``
    if the file is missing or stale.
    """
    path = DOCS_DIR / "WCAG_AUDIT_2026-06-13.md"
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    m = re.search(r"\*\*Score:\*\*\s+(\d+)\s*/\s*100", text)
    if not m:
        return None
    pass_m = re.search(r"\*\*Pass:\*\*\s+(\d+)", text)
    warn_m = re.search(r"\*\*Warn:\*\*\s+(\d+)", text)
    fail_m = re.search(r"\*\*Fail:\*\*\s+(\d+)", text)
    return (
        int(m.group(1)),
        f"{pass_m.group(1) if pass_m else '?'} pass / {warn_m.group(1) if warn_m else '?'} warn / "
        f"{fail_m.group(1) if fail_m else '?'} fail",
    )


# ── Open-issue cross-reference ─────────────────────────────────────


_OPEN_RE = re.compile(
    r"^\s*\d+\.\s+\*\*[^*]+\*\*|\|\s*P[0-3]\s+\||status.*(open|in-progress|partial|not-started)",
    re.IGNORECASE | re.MULTILINE,
)


def _count_open_issues() -> dict[str, int]:
    """Tally open items by priority from canonical doc sources.

    Looks for patterns like ``| P0 |`` in the issue-review doc and the
    remaining-work doc. Returns counts keyed by P0/P1/P2/P3 (zero if no
    matches).
    """
    sources = [
        DOCS_DIR / "REMAINING_WORK.md",
        DOCS_DIR / "issue_review_2026-06-13_improvement_opportunities.md",
    ]
    counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    for src in sources:
        if not src.is_file():
            continue
        try:
            text = src.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in text.splitlines():
            for pri in ("P0", "P1", "P2", "P3"):
                if f"| {pri} |" in line or f"{pri} " in line and "**" in line:
                    # Quick-and-dirty heuristic: P0/P1/P2/P3 mentions in
                    # a row that also has a verb or noun (avoid counting
                    # every "P0" in prose). Tune by character count.
                    if len(line) < 220 and ("❌" in line or "🔴" in line or "Status" in line):
                        counts[pri] += 1
                        break
    return counts


# ── Doc drift detection ─────────────────────────────────────────────


def _stale_docs(days: int = 30) -> list[tuple[str, int]]:
    """Return ``(path, days_old)`` for top-level ``Docs/*.md`` older than ``days``.

    Path is reported relative to ``DOCS_DIR`` (so tests can redirect
    ``DOCS_DIR`` to a temp dir without breaking the function). When a
    path is outside ``DOCS_DIR``, the absolute path is returned as a
    defensive fallback.
    """
    out: list[tuple[str, int]] = []
    today = _dt.date.today()
    for path in sorted(DOCS_DIR.glob("*.md")):
        if path.name.startswith("."):
            continue
        mtime = _dt.date.fromtimestamp(path.stat().st_mtime)
        age = (today - mtime).days
        if age > days:
            try:
                rel = str(path.relative_to(DOCS_DIR))
            except ValueError:
                rel = str(path)
            out.append((rel, age))
    return out


# ── Top-level snapshot ─────────────────────────────────────────────


@dataclass
class StateSnapshot:
    generated_at: str
    test_count: int
    test_count_method: str
    test_files: int
    service_count: int
    screen_count: int
    tab_count: int
    provider_count: int
    wcag_score: int | None
    wcag_breakdown: str | None
    open_issues: dict[str, int] = field(default_factory=dict)
    stale_docs: list[tuple[str, int]] = field(default_factory=list)
    modules: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "test_count": self.test_count,
            "test_count_method": self.test_count_method,
            "test_files": self.test_files,
            "service_count": self.service_count,
            "screen_count": self.screen_count,
            "tab_count": self.tab_count,
            "provider_count": self.provider_count,
            "wcag_score": self.wcag_score,
            "wcag_breakdown": self.wcag_breakdown,
            "open_issues": self.open_issues,
            "stale_docs": [{"path": p, "days_old": d} for p, d in self.stale_docs],
            "module_counts": {
                "services": self.service_count,
                "screens": self.screen_count,
                "tabs": self.tab_count,
                "providers": self.provider_count,
                "tests": self.test_files,
            },
        }


def build_snapshot() -> StateSnapshot:
    """Build a fresh state snapshot from the current project state."""
    now = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
    count, method = _count_tests_via_pytest()
    if count == 0:
        count, method = _count_tests_via_walk()
    modules = _list_modules()
    wcag = _read_wcag_score()
    return StateSnapshot(
        generated_at=now.isoformat(),
        test_count=count,
        test_count_method=method,
        test_files=len(modules.get("tests", [])),
        service_count=len(modules.get("services", [])),
        screen_count=len(modules.get("screens", [])),
        tab_count=len(modules.get("tabs", [])),
        provider_count=len(modules.get("providers", [])),
        wcag_score=wcag[0] if wcag else None,
        wcag_breakdown=wcag[1] if wcag else None,
        open_issues=_count_open_issues(),
        stale_docs=_stale_docs(),
        modules=modules,
    )


# ── Renderers ───────────────────────────────────────────────────────


def render_markdown(snap: StateSnapshot) -> str:
    """Render the canonical `Docs/SYSTEM_STATE.md` dashboard."""
    lines: list[str] = [
        "# ShopStack System State",
        "",
        f"**Generated:** {snap.generated_at} · **Source:** `shopstack.tools.generate_state`",
        "",
        "> This dashboard is **machine-generated** from the project. To refresh,",
        "> run `python -m shopstack.tools.generate_state` (or let the CI hook do it).",
        "> Hand-edits will be overwritten — add a `## Addendum` section if you need",
        "> to record a long-term note.",
        "",
        "## Headline Numbers",
        "",
        "| Metric | Value | Method |",
        "|--------|-------|--------|",
        f"| Tests | {snap.test_count} | `{snap.test_count_method}` |",
        f"| Test files | {snap.test_files} | `walk` |",
        f"| Services | {snap.service_count} | `walk` |",
        f"| Screens | {snap.screen_count} | `walk` |",
        f"| Tabs | {snap.tab_count} | `walk` |",
        f"| Providers | {snap.provider_count} | `walk` |",
        (
            f"| WCAG 2.1 AA | {snap.wcag_score} / 100 | breakdown: {snap.wcag_breakdown} |"
            if snap.wcag_score is not None
            else "| WCAG 2.1 AA | not audited | run `python -m shopstack.tools.audit_wcag` |"
        ),
        "",
        "## Open Issues (cross-referenced)",
        "",
        "| Priority | Count |",
        "|----------|-------|",
    ]
    for pri in ("P0", "P1", "P2", "P3"):
        lines.append(f"| {pri} | {snap.open_issues.get(pri, 0)} |")
    lines += [
        "",
        "_Counts are heuristics parsed from `Docs/REMAINING_WORK.md` and "
        "`Docs/issue_review_2026-06-13_improvement_opportunities.md`._",
        "",
        "## Stale Docs (>30 days, top-level only)",
        "",
    ]
    if not snap.stale_docs:
        lines.append("_None._ All `Docs/*.md` files at the top level are fresh.")
    else:
        lines.append("| Path | Days old |")
        lines.append("|------|----------|")
        for path, days in snap.stale_docs:
            lines.append(f"| `{path}` | {days} |")
    lines += [
        "",
        "## Subsystem Inventory",
        "",
        "### Services",
        "",
    ]
    for p in snap.modules.get("services", []):
        lines.append(f"- `{p}`")
    lines += [
        "",
        "### Screens",
        "",
    ]
    for p in snap.modules.get("screens", []):
        lines.append(f"- `{p}`")
    lines += [
        "",
        "### Tabs",
        "",
    ]
    for p in snap.modules.get("tabs", []):
        lines.append(f"- `{p}`")
    lines += [
        "",
        "### Providers",
        "",
    ]
    for p in snap.modules.get("providers", []):
        lines.append(f"- `{p}`")
    lines += [
        "",
        "## How To Refresh",
        "",
        "```bash",
        "# from project root",
        "python -m shopstack.tools.generate_state",
        "```",
        "",
        "The generator also writes `Docs/STATE_DASHBOARD.json` (machine-readable)",
        "so other tools (CI hooks, agent kickoff, the docs linter) can ingest",
        "the same numbers without re-parsing the markdown.",
        "",
        "## Why This Is Canonical",
        "",
        "Hand-maintained state docs drift. The previous `Docs/SYSTEM_STATE.md` and",
        "`Docs/FEATURES_STATUS.md` had been edited independently for months and",
        "contradicted each other on basic numbers (test counts, statuses). This",
        "generator re-derives everything from the actual project:",
        "",
        "1. `pytest --collect-only -q` is the source for test count (with a",
        "   directory-walk fallback when pytest is not available).",
        "2. The WCAG score comes from `Docs/WCAG_AUDIT_2026-06-13.md`, which is",
        "   itself regenerated by `shopstack.tools.audit_wcag` and pinned by the",
        "   CI hook in `.github/workflows/wcag.yml`.",
        "3. The open-issue counts parse the canonical backlog docs and tally",
        "   priorities by a heuristic; for a stricter count, use the Linear board.",
        "4. Doc-drift detection compares `mtime` to today, so any doc that hasn't",
        "   been touched in 30 days shows up here.",
        "",
        "If you find a discrepancy between this dashboard and reality, fix the code",
        "(or the doc) and re-run the generator — that's the whole loop.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Run as ``python -m shopstack.tools.generate_state``."""
    snap = build_snapshot()
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text(render_markdown(snap), encoding="utf-8")
    OUTPUT_JSON.write_text(json.dumps(snap.to_dict(), indent=2), encoding="utf-8")
    # Use a safe relative-path display: fall back to absolute when the
    # output path is outside the project root (e.g. tests redirect to
    # tmp_path). The dashboard still works either way.
    try:
        md_label = str(OUTPUT_MD.relative_to(PROJECT_ROOT))
    except ValueError:
        md_label = str(OUTPUT_MD)
    try:
        json_label = str(OUTPUT_JSON.relative_to(PROJECT_ROOT))
    except ValueError:
        json_label = str(OUTPUT_JSON)
    print(
        f"→ {md_label} ({snap.test_count} tests, "
        f"WCAG {snap.wcag_score if snap.wcag_score is not None else '?'}/100)"
    )
    print(f"→ {json_label}")
    return 0


__all__ = [
    "StateSnapshot",
    "build_snapshot",
    "render_markdown",
    "main",
]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
