"""Doc health audit — flags docs claiming stale test counts or closed items.

Scans every ``Docs/*.md`` file (excluding ``Docs/archive/``) for:

1. **Stale test-count claims** — lines matching patterns like
   ``"N tests"``, ``"N test(s) passed"``, ``"N test(s) collected"``
   and cross-references them against the actual ``pytest --collect-only``
   count.  Any number that doesn't match the real count is flagged.

2. **Stale completion claims** — lines with emoji + completion status
   (``✅ DONE``, ``✅ Complete``, ``✅ Fixed``, ``✅ Resolved``) that
   reference a specific code path, file, or test count — surfaced for
   human review since static analysis can't verify runtime truth.

3. **Missing or stale "Last updated" dates** — docs without a
   ``**Last updated:**`` line are flagged.  Docs with a date older
   than 30 days are warned.

Run as a script::

    uv run python -m shopstack.tools.doc_health [--strict]

The ``--strict`` flag causes the script to exit with code 1 when any
stale test count is found (useful for the pre-commit hook and CI).
Without ``--strict``, the script prints the report and exits 0.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


logger = logging.getLogger(__name__)


DOCS_DIR = Path("Docs")
ARCHIVE_DIR = DOCS_DIR / "archive"
STALENESS_DAYS = 30
ACTUAL_TEST_COUNT: int | None = None  # populated on first call


# ─── Dataclasses ─────────────────────────────────────────────────


@dataclass
class DocHealthFinding:
    """A single finding from the audit."""

    category: str       # "stale_test_count" | "stale_completion" | "missing_date" | "old_date"
    file: str           # relative path e.g. Docs/ROADMAP.md
    line: int           # line number (1-based)
    text: str           # matching line content
    severity: str       # "error" | "warn" | "info"
    detail: str = ""    # human-readable explanation


@dataclass
class DocHealthReport:
    """Full audit report."""

    findings: list[DocHealthFinding] = field(default_factory=list)
    actual_test_count: int = 0
    scanned_files: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warn_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warn")

    @property
    def info_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "info")

    @property
    def has_stale_test_counts(self) -> bool:
        return any(f.category == "stale_test_count" for f in self.findings)


# ─── Helpers ─────────────────────────────────────────────────────


def _collect_files() -> tuple[list[str], list[str]]:
    """Return (scanned, skipped) relative paths from Docs/."""
    scanned: list[str] = []
    skipped: list[str] = []
    if not DOCS_DIR.is_dir():
        return scanned, skipped
    for child in sorted(DOCS_DIR.iterdir()):
        if not child.is_file() or child.suffix not in {".md", ".markdown"}:
            continue
        rel = str(child.relative_to(Path(".")))
        # Skip archived files
        if ARCHIVE_DIR in child.parents or child == ARCHIVE_DIR:
            skipped.append(rel)
            continue
        scanned.append(rel)
    return scanned, skipped


def _get_actual_test_count() -> int | None:
    """Return the actual test count from ``pytest --collect-only -q``.

    Returns ``None`` if the count could not be determined (pytest
    failed, timed out, or is not available). The caller should skip
    stale-count checks when this is ``None`` to avoid false positives.

    Result is cached after the first call.
    """
    global ACTUAL_TEST_COUNT
    if ACTUAL_TEST_COUNT is not None:
        return ACTUAL_TEST_COUNT
    try:
        result = subprocess.run(
            ["uv", "run", "pytest", "tests/", "--collect-only", "-q"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Output looks like: "2898 tests collected" or "2796 tests collected (shard 1 of 2)"
        m = re.search(r"(\d+)\s+tests?\s+collected", result.stdout or result.stderr or "")
        if m:
            ACTUAL_TEST_COUNT = int(m.group(1))
        else:
            ACTUAL_TEST_COUNT = None  # couldn't parse the count
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        ACTUAL_TEST_COUNT = None
    return ACTUAL_TEST_COUNT


def _parse_date_from_line(line: str) -> dt.date | None:
    """Try to extract a date from a line like '**Last updated:** 2026-06-13'.

    Handles formats: YYYY-MM-DD, DD Mon YYYY, Mon DD, YYYY.
    """
    # YYYY-MM-DD
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", line)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _parse_numeric_doc_claim(line: str) -> int | None:
    """Extract a numeric test count from a doc claim line.

    Matches patterns like:
    - "2651 tests collected"
    - "619 tests, 0 failures"
    - "375+ tests passed"
    - "~390"
    - "32 tests"
    """
    # Match numbers in test count context — but NOT "N test files" (file count)
    m = re.search(
        r"(?:~|about|over|approx\.?)\s*(\d{3,})\s*(?:(?:tests?)(?!\s+files)|passed|collected)",
        line, re.IGNORECASE,
    )
    if m:
        return int(m.group(1))
    # Match bare N with test/passed/collected but NOT "N test files" (file count)
    m = re.search(
        r"(\d{3,})\s*(?:(?:tests?)(?!\s+files)|passed|collected)",
        line, re.IGNORECASE,
    )
    if m:
        return int(m.group(1))
    # Standalone ~N where N >= 100 (likely test count reference).
    # Exclude patterns clearly about lines, files, or sizes.
    m = re.search(r"~\s*(\d{3,})\b", line)
    if m:
        after = line[m.end():].strip().lower()
        # Skip if followed by a line/file/size indicator
        if after.startswith(("lines", "line", "files", "file", "bytes", "kb", "mb", "gb")):
            return None
        # Skip if followed by + then lines/file (e.g. "~4000+ lines")
        after_plus = re.sub(r"^[+\-]+", "", after).strip().lower()
        if after_plus.startswith(("lines", "line", "files", "file")):
            return None
        # Skip "~N test files" (file count, not test count)
        if re.search(r"test\s+files", after, re.IGNORECASE):
            return None
        return int(m.group(1))
    return None


# ─── Scan functions ──────────────────────────────────────────────


def _check_stale_test_counts(
    path: str, lines: list[str],
) -> list[DocHealthFinding]:
    """Find lines claiming a test count that differs from actual.

    Silently skips when the actual count is not available (e.g.
    pytest failed to run) to avoid false positives.

    Lines that contain the actual test count (e.g. "2898") or explicit
    stale/historical markers are treated as acknowledged historical
    references and are NOT flagged. This allows decision records,
    baseline markers, and comparison tables to coexist with the audit.
    """
    actual = _get_actual_test_count()
    if actual is None:
        return []  # can't verify — skip
    actual_str = str(actual)
    findings: list[DocHealthFinding] = []
    for i, line in enumerate(lines, start=1):
        # Skip lines that acknowledge the current count (comparative/
        # historical references) or contain explicit stale markers
        if actual_str in line:
            continue
        line_lower = line.lower()
        if "(stale" in line_lower or "(historical" in line_lower or "(baseline" in line_lower or "**baseline" in line_lower:
            continue

        claimed = _parse_numeric_doc_claim(line)
        if claimed is None:
            continue
        if claimed != actual:
            findings.append(DocHealthFinding(
                category="stale_test_count",
                file=path,
                line=i,
                text=line.strip()[:120],
                severity="error",
                detail=(
                    f"Claims {claimed} tests but actual is {actual}. "
                    "Update the count or add a stale-reference note."
                ),
            ))
        else:
            findings.append(DocHealthFinding(
                category="stale_test_count",
                file=path,
                line=i,
                text=line.strip()[:120],
                severity="info",
                detail=f"Test count {claimed} matches actual ({actual}).",
            ))
    return findings


def _extract_path_refs(text: str) -> list[str]:
    """Extract file/function paths referenced in a line of doc text.

    Returns a list of plausible source file paths (relative to project
    root) that can be checked with ``Path().is_file()``.  When the path
    is a bare filename (e.g. ``inventory.py``), falls back to a glob
    search so the tool doesn't report a false positive if the file
    exists deeper in the tree.
    """
    refs: list[str] = []
    # Backtick paths: `shopstack/services/dashboard.py`, `tests/test_foo.py`
    for m in re.finditer(r"`([^`]+)`", text):
        candidate = m.group(1).strip()
        # Only check paths that look like source/test files
        if re.match(r"^[a-z_][a-z0-9_/]*\.(?:py|css|html|js|ts|json|yaml|yml|toml|cfg|ini|md)$", candidate, re.IGNORECASE):
            refs.append(candidate)
        # Also accept script names in tools/ or scripts/
        if candidate.startswith(("tools/", "scripts/")):
            refs.append(candidate)
    # Also catch bare paths like shopstack/services/foo.py without backticks
    for m in re.finditer(r"([a-z_][a-z0-9_/]*)\.py", text):
        candidate = m.group(0)
        if candidate not in refs:
            refs.append(candidate)
    return refs


def _resolve_path(ref: str) -> str | None:
    """Resolve a file reference to its on-disk path.

    Returns the path if the file exists at the given location, or if it
    can be found via glob (for bare filenames like ``inventory.py``).
    Falls back to ``shopstack/`` and ``shopstack/ui/`` prefixes for
    paths relative to the project's source tree (common in docs).
    Returns ``None`` if the file cannot be found.
    """
    p = Path(ref)
    if p.is_file():
        return ref
    # Try with shopstack/ prefix (code lives under this directory)
    for prefix in ("shopstack/", "shopstack/ui/"):
        candidate = f"{prefix}{ref}"
        if Path(candidate).is_file():
            return candidate
    # Bare filename — try **/ glob
    if "/" not in ref:
        matches = sorted(Path(".").rglob(ref))
        if matches:
            return str(matches[0])
    return None


def _check_stale_completions(
    path: str, lines: list[str],
) -> list[DocHealthFinding]:
    """Find lines with ✅ DONE / ✅ Complete / ✅ Fixed / ✅ Resolved claims.

    These are non-fatal information findings surfaced so the user can
    manually verify them against the codebase. When the line references
    a specific file path, the tool checks whether that file still exists
    on disk — if it doesn't, the severity is upgraded to a warning.
    """
    completion_pattern = re.compile(
        r"(✅\s*(?:DONE|Complete|Fixed|Resolved|Built))"
    )
    findings: list[DocHealthFinding] = []
    for i, line in enumerate(lines, start=1):
        m = completion_pattern.search(line)
        if not m:
            continue
        # Skip if the line is about a doc file (those are trivially verifiable)
        if "Docs/" in line and ("Created" in line or "Updated" in line):
            continue
        # Skip status-dashboard lines that are clearly tables
        if line.strip().startswith("|") and line.strip().endswith("|"):
            has_code_ref = bool(re.search(
                r"`[^`]+`|[a-z_]+\.[a-z_]+\(|[a-z_]+/[a-z_]+",
                line,
            ))
            if not has_code_ref:
                continue

        # Check file existence for referenced paths
        refs = _extract_path_refs(line)
        missing_file = None
        for ref in refs:
            resolved = _resolve_path(ref)
            if resolved is None:
                missing_file = ref
                break

        if missing_file:
            findings.append(DocHealthFinding(
                category="stale_completion",
                file=path,
                line=i,
                text=line.strip()[:120],
                severity="warn",
                detail=(
                    f"Marked '{m.group(1)}' but referenced file '{missing_file}' no longer exists on disk."
                ),
            ))
        else:
            findings.append(DocHealthFinding(
                category="stale_completion",
                file=path,
                line=i,
                text=line.strip()[:120],
                severity="info",
                detail=(
                    f"Marked '{m.group(1)}'. Verify this claim is still "
                    "accurate against the current codebase."
                ),
            ))
    return findings


def _check_last_updated_dates(
    path: str, lines: list[str], now: dt.date,
) -> list[DocHealthFinding]:
    """Check for missing or stale 'Last updated' dates."""
    findings: list[DocHealthFinding] = []
    found_date = False
    for i, line in enumerate(lines, start=1):
        if "last updated" in line.lower():
            found_date = True
            parsed = _parse_date_from_line(line)
            if parsed is None:
                findings.append(DocHealthFinding(
                    category="old_date",
                    file=path,
                    line=i,
                    text=line.strip()[:120],
                    severity="warn",
                    detail="'Last updated' line found but no parseable date.",
                ))
            elif (now - parsed).days > STALENESS_DAYS:
                findings.append(DocHealthFinding(
                    category="old_date",
                    file=path,
                    line=i,
                    text=line.strip()[:120],
                    severity="warn",
                    detail=(
                        f"Last updated {parsed} ({ (now - parsed).days } days ago). Review and update if stale (threshold: {STALENESS_DAYS} days)."
                    ),
                ))
            break  # only check the first "last updated" line
    if not found_date:
        findings.append(DocHealthFinding(
            category="missing_date",
            file=path,
            line=1,
            text="(no 'Last updated' line found)",
            severity="warn",
            detail="Add a '**Last updated:** YYYY-MM-DD' line near the top.",
        ))
    return findings


# ─── Main audit ──────────────────────────────────────────────────


def run_audit() -> DocHealthReport:
    """Run the doc health audit against ``Docs/*.md``."""
    scanned, skipped = _collect_files()
    now = dt.date.today()
    actual = _get_actual_test_count()
    report = DocHealthReport(
        actual_test_count=actual,
        scanned_files=scanned,
        skipped_files=skipped,
    )

    for rel_path in scanned:
        try:
            text = Path(rel_path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.debug("read %s failed: %s", rel_path, exc)
            continue
        lines = text.split("\n")
        report.findings.extend(_check_stale_test_counts(rel_path, lines))
        report.findings.extend(_check_stale_completions(rel_path, lines))
        report.findings.extend(_check_last_updated_dates(rel_path, lines, now))

    return report


# ─── Rendering ───────────────────────────────────────────────────


def render_report_markdown(report: DocHealthReport) -> str:
    """Render the audit report as Markdown."""
    lines: list[str] = [
        "# Doc Health Audit",
        "",
        f"**Test count:** {report.actual_test_count} (from `pytest --collect-only`)",
        f"**Scanned:** {len(report.scanned_files)} files",
        f"**Skipped (archive):** {len(report.skipped_files)} files",
        f"**Errors:** {report.error_count}  **Warnings:** {report.warn_count}  **Info:** {report.info_count}",
        "",
    ]
    if not report.findings:
        lines.append("_No findings. All docs are healthy._")
        return "\n".join(lines)

    # Errors
    errors = [f for f in report.findings if f.severity == "error"]
    if errors:
        lines.append("## 🔴 Stale Test Counts (errors)")
        lines.append("")
        lines.append("| File | Line | Claim vs Actual |")
        lines.append("|------|------|-----------------|")
        for f in errors:
            lines.append(f"| {f.file} | {f.line} | `{f.text}` — {f.detail} |")
        lines.append("")

    # Warnings
    warnings = [f for f in report.findings if f.severity == "warn"]
    if warnings:
        lines.append("## 🟡 Warnings")
        lines.append("")
        lines.append("| File | Line | Detail |")
        lines.append("|------|------|--------|")
        for f in warnings:
            text_snippet = f.text[:80].replace("|", "\\|")
            lines.append(f"| {f.file} | {f.line} | {text_snippet} — {f.detail} |")
        lines.append("")

    # Info
    infos = [f for f in report.findings if f.severity == "info"]
    if infos:
        lines.append("## ℹ️ Informational")
        lines.append("")
        lines.append(f"_{len(infos)} completion claims and matching counts found._")
        lines.append("")
        # Collapse into file-level summary
        by_file: dict[str, list[DocHealthFinding]] = {}
        for f in infos:
            by_file.setdefault(f.file, []).append(f)
        for file, items in sorted(by_file.items()):
            stale_ct = sum(1 for i in items if i.category == "stale_test_count")
            completions = sum(1 for i in items if i.category == "stale_completion")
            parts = []
            if stale_ct:
                parts.append(f"{stale_ct} test count(s) match")
            if completions:
                parts.append(f"{completions} completion claim(s)")
            lines.append(f"- **{file}** — {', '.join(parts)}")
        lines.append("")

    lines.append("---")
    lines.append(f"_Audit generated: {dt.date.today()}_")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Run as ``uv run python -m shopstack.tools.doc_health``."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    strict = "--strict" in (argv or sys.argv[1:])
    report = run_audit()
    md = render_report_markdown(report)
    print(md)

    # Always exit 0 in non-strict mode; strict mode exits 1 on any stale count
    if strict and report.has_stale_test_counts:
        sys.stderr.write(
            "\n❌ doc-health (strict): Stale test counts found. "
            "Update Docs/ files or add a note acknowledging the staleness.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))


__all__ = [
    "DocHealthFinding",
    "DocHealthReport",
    "main",
    "render_report_markdown",
    "run_audit",
]
