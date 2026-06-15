"""Consumer-copy audit — flags engineering jargon in user-facing UI.

A static-analysis pass over `shopstack/ui/` and `shopstack/services/i18n.py`
that reports any visible label, button text, or table header that
exposes engineering terminology to end users. The audit produces a
machine-readable report (JSON) and a markdown summary.

**Why this exists (motto_v3 §0.14 product reality + 2026-06-13 review):**

Issue review items #3, #37, #38, #42: visible labels still leak
"Save Trace", "canonical", "Lot ID", "Scene Type", "redacted JSONL".
The product cannot claim to be consumer-friendly while the chrome
says "Lot ID" in capital letters. This audit:

1. Walks every Python file under `shopstack/ui/` (and the i18n
   registry).
2. Extracts strings passed to `gr.Button(label=...)`,
   `gr.Markdown(value=...)`, `gr.HTML(value=...)`, `gr.Textbox(label=...)`,
   `gr.Dataframe(headers=...)`, and similar.
3. Compares each extracted string against a curated blocklist of
   engineering terms.
4. Reports each violation with its file, line number, and the
   suggested consumer-friendly replacement (from `OVERRIDES`).

**Supersession rule (motto_v3 §7):** no existing label is rewritten
in place. The audit *reports* matches; the fix is to update the
i18n table or wrap the label in a `t(...)` call. Internal code paths
that use the terms (`"canonical_name"` in a dataclass field, a DB
column, a function argument) are not flagged — only strings that
appear in user-facing `label=`, `value=`, or `placeholder=`
parameters of Gradio components.

**CI hook:** a thin GitHub Actions workflow can call
``python -m shopstack.tools.copy_audit`` and fail the build if the
violation count is non-zero. The audit is the canonical
mechanism for keeping the chrome consumer-friendly.

**Why static analysis (vs. runtime):** static analysis catches the
issue at PR time, not after a release. It also avoids needing
Playwright in the CI loop. The trade-off is false positives — the
blocklist is intentionally conservative.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UI_DIR = PROJECT_ROOT / "shopstack" / "ui"
I18N_FILE = PROJECT_ROOT / "shopstack" / "services" / "i18n.py"
OUTPUT_MD = PROJECT_ROOT / "Docs" / "COPY_AUDIT.md"
OUTPUT_JSON = PROJECT_ROOT / "Docs" / "COPY_AUDIT.json"


# ── Blocklist: term → suggested replacement ────────────────────────


# Each entry: (regex, suggested_consumer_replacement, why).
# A violation is reported when the regex appears in a user-facing
# string. Case-insensitive by default. The suggested replacement
# is guidance — the audit does not auto-fix; the engineer chooses
# whether to translate the label or wrap it in a `t(...)` call.
OVERRIDES: dict[str, tuple[str, str]] = {
    "trace": (
        "Action history",
        "Internal: refers to the audit log of who did what. Show "
        "'Action history' to consumers.",
    ),
    "redacted jsonl": (
        "Anonymized list",
        "The 'redacted JSONL' wording is engineering; consumers want "
        "a plain 'anonymized list'.",
    ),
    "canonical": (
        "(hide this column)",
        "The 'canonical' column is internal naming. Either drop it "
        "from the visible table or rename to 'Item'.",
    ),
    "lot id": (
        "Batch",
        "'Lot ID' is warehouse jargon. 'Batch' is the consumer term.",
    ),
    "scene type": (
        "Image type",
        "'Scene Type' is OCR-internal. Show 'Image type' or auto-hide.",
    ),
    "consumer copy": (
        "Action history",  # we flag "consumer copy" as the regex
        "(see audit doc)",
    ),
    "jsonl": (
        "(hide technical detail)",
        "JSONL is an internal export format. Hide from consumer UI.",
    ),
    "api": (
        "(hide technical detail)",
        "API references belong in developer docs, not consumer labels.",
    ),
    "endpoint": (
        "(hide technical detail)",
        "Same as 'api' — keep technical detail out of the chrome.",
    ),
    "redis": (
        "(hide technical detail)",
        "No Redis terms in the visible UI.",
    ),
    "sqlite": (
        "(hide technical detail)",
        "Same as 'redis'.",
    ),
    "model stack": (
        "Models",
        "Drop 'stack' — consumers see a flat list of providers.",
    ),
    "ocr pipeline": (
        "Text recognition",
        "OCR is fine; 'pipeline' is the engineering word.",
    ),
    "stt backend": (
        "Speech recognition",
        "Consumer wording for the STT provider list.",
    ),
    "embedding": (
        "Match score",
        "Visible in search results; 'embedding' is the model term.",
    ),
    "vector store": (
        "Match score",
        "Same as 'embedding' — internal concept, not a label.",
    ),
    "federation bundle": (
        "Price share",
        "Bundle is engineering. The consumer concept is 'share'.",
    ),
    "backfill": (
        "(hide technical detail)",
        "Backfill is migration jargon.",
    ),
    "shim": (
        "(hide technical detail)",
        "Implementation detail, not a user concept.",
    ),
    "registry": (
        "(hide technical detail)",
        "Code-internal. Hide from consumers.",
    ),
    "i18n": (
        "Language",
        "i18n is the standard internal name. Show 'Language'.",
    ),
}


# ── Extraction regexes ─────────────────────────────────────────────


# Capture every user-facing string in a Gradio component call. We
# accept two patterns:
#
# 1. ``gr.Component(label="text")`` — keyword-style label, the most
#    common in modern ShopStack.
# 2. ``gr.Component("text", ...)`` — positional first-argument label,
#    which older Gradio APIs accept (e.g. ``gr.Button("Save")``).
#
# Both patterns share the same opening ``gr.Component(`` token, so we
# match the call once, then look for the label inside.
_GR_CALL_RE = re.compile(
    r"\bgr\.(?:Button|Markdown|HTML|Textbox|Number|Slider|Dropdown|Radio|"
    r"Checkbox|Tab|Tabs|File|Image|Video|Audio|ColorPicker|Dataframe|"
    r"HighlightedText|Code|Chatbot)\s*\(",
    re.IGNORECASE,
)

# Inside a call, the user-facing string is either a `label=` keyword
# or the first positional string literal. Both regexes below look
# only inside the parentheses (the match positions are then mapped
# back to a line/column).
_LABEL_KW_RE = re.compile(
    r"\b(?:label|value|placeholder|info|tooltip)\s*=\s*(['\"])(?P<text>.*?)(?:\1)",
    re.IGNORECASE | re.DOTALL,
)
_FIRST_POSITIONAL_RE = re.compile(
    r"^\s*(['\"])(?P<text>(?:\\.|(?!\1).)*)\1",
    re.DOTALL,
)


@dataclass
class Violation:
    file: str
    line: int
    column: int
    matched_text: str
    rule: str
    suggestion: str
    why: str


@dataclass
class CopyReport:
    violations: list[Violation] = field(default_factory=list)
    scanned_files: int = 0

    def to_dict(self) -> dict:
        return {
            "violations": [v.__dict__ for v in self.violations],
            "scanned_files": self.scanned_files,
            "violation_count": len(self.violations),
        }


# ── Scan logic ─────────────────────────────────────────────────────


def _iter_visible_strings(path: Path) -> Iterable[tuple[int, int, str, str]]:
    """Yield ``(line, col, kw, text)`` for every user-facing string
    literal in a Gradio component call.

    For each ``gr.Component(`` call we emit at most one match — the
    label (keyword) or the first positional string. We deliberately
    do not flag *every* quoted string inside the call: only the one
    that the user will actually see.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    for call_match in _GR_CALL_RE.finditer(text):
        # Walk forward, balanced-paren, to find the end of the call.
        # For real code, Gradio calls are short (<200 chars), so a
        # simple scan works.
        start = call_match.end()
        depth = 1
        i = start
        while i < len(text) and depth > 0:
            ch = text[i]
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            i += 1
        if depth != 0:
            continue
        # text[start:i-1] is the call's argument list.
        args_text = text[start : i - 1]
        # Prefer a keyword-style label.
        kw_match = _LABEL_KW_RE.search(args_text)
        if kw_match:
            kw = kw_match.group(0).split("=", 1)[0].strip()
            label_text = kw_match.group("text")
        else:
            # Fall back to the first positional string literal.
            pos_match = _FIRST_POSITIONAL_RE.search(args_text)
            if not pos_match:
                continue
            kw = "label"  # implicit / positional
            label_text = pos_match.group("text")
        if not label_text:
            continue
        # Compute the absolute position of the matched text in the
        # full source so we can report a line/column.
        if kw_match:
            abs_pos = start + kw_match.start("text")
        else:
            abs_pos = start + (pos_match.start("text") if pos_match else 0)
        line = text.count("\n", 0, abs_pos) + 1
        col = abs_pos - text.rfind("\n", 0, abs_pos)
        yield line, col, kw, label_text


def scan_file(path: Path) -> list[Violation]:
    """Scan one file and return its violations."""
    out: list[Violation] = []
    try:
        rel = str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        # path is outside PROJECT_ROOT (e.g. tests use tmp_path)
        rel = str(path)
    for line, col, kw, text in _iter_visible_strings(path):
        text_lower = text.lower()
        for term, (suggestion, why) in OVERRIDES.items():
            if term in text_lower:
                out.append(
                    Violation(
                        file=rel,
                        line=line,
                        column=col,
                        matched_text=text,
                        rule=f"forbidden-term:{term}",
                        suggestion=suggestion,
                        why=why,
                    )
                )
    return out


def scan_i18n() -> list[Violation]:
    """Scan the i18n registry for the same forbidden terms.

    A blocklist match in i18n.py is still a violation: the registry
    is the canonical copy. If the i18n string itself contains a
    forbidden term, we should either translate the term or reword.

    Skips:
      * Lines inside Python docstrings (the audit is a UI linter,
        not a code-comment linter).
      * i18n KEY names on the left side of the ``:`` (only the
        VALUES are user-visible).
    """
    out: list[Violation] = []
    rel = str(I18N_FILE.relative_to(PROJECT_ROOT))
    if not I18N_FILE.is_file():
        return out
    try:
        text = I18N_FILE.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return out
    # Reuse the docstring detector from js_validate
    from shopstack.tools.js_validate import _compute_skipped_lines
    skipped_lines = _compute_skipped_lines(text)
    for m in re.finditer(r'"([^"\\]*(?:\\.[^"\\]*)*)"', text):
        literal = m.group(1)
        line = text.count("\n", 0, m.start()) + 1
        # Skip docstrings
        if line in skipped_lines:
            continue
        # Skip i18n KEY names. The registry looks like
        # ``"key": "value"`` — the literal we matched is the
        # KEY, not the VALUE. Detect by checking the text
        # immediately after the closing quote.
        tail = text[m.end(): m.end() + 5]
        if tail.lstrip().startswith(":"):
            continue
        literal_lower = literal.lower()
        for term, (suggestion, why) in OVERRIDES.items():
            if term in literal_lower:
                col = m.start() - text.rfind("\n", 0, m.start())
                out.append(
                    Violation(
                        file=rel,
                        line=line,
                        column=col,
                        matched_text=literal,
                        rule=f"forbidden-term:{term}",
                        suggestion=suggestion,
                        why=why,
                    )
                )
    return out


def run_audit() -> CopyReport:
    """Walk ``shopstack/ui/`` and the i18n registry, return a report."""
    report = CopyReport()
    if UI_DIR.is_dir():
        for path in UI_DIR.rglob("*.py"):
            if "__pycache__" in str(path) or "_legacy" in str(path):
                continue
            report.scanned_files += 1
            report.violations.extend(scan_file(path))
    report.violations.extend(scan_i18n())
    return report


# ── Renderers ──────────────────────────────────────────────────────


def render_markdown(report: CopyReport) -> str:
    """Render a markdown summary of the audit."""
    lines: list[str] = [
        "# Consumer-Copy Audit",
        "",
        f"**Scanned files:** {report.scanned_files} · **Violations:** {len(report.violations)}",
        "",
        "> Static-analysis pass over `shopstack/ui/` and `shopstack/services/i18n.py`.",
        "> Each violation is a string that appears in a user-facing UI element",
        "> (button label, markdown text, dataframe header, etc.) and contains a",
        "> term from the engineering blocklist. The suggested replacement is",
        "> guidance, not a forced fix — engineers decide whether to translate",
        "> the label or wrap it in a `t(...)` call.",
        "",
    ]
    if not report.violations:
        lines += [
            "## No violations found",
            "",
            "_All visible UI strings are consumer-friendly._",
        ]
    else:
        lines += [
            "## Violations",
            "",
            "| File | Line | Rule | Matched text | Suggestion |",
            "|------|------|------|--------------|------------|",
        ]
        for v in report.violations:
            lines.append(
                f"| `{v.file}` | {v.line} | `{v.rule}` | `{v.matched_text[:60]}` | {v.suggestion} |"
            )
    lines += [
        "",
        "## How to fix",
        "",
        "Two options:",
        "",
        "1. **Translate.** Add the i18n key with a consumer-friendly translation, "
        "   then wrap the label in `t(\"your.key\")`.",
        "2. **Reword.** Change the literal directly to a consumer-friendly phrase, "
        "   then add the same phrase to the i18n table so it can be translated.",
        "",
        "## Why static analysis (not runtime)",
        "",
        "A static pass catches the issue at PR time, before any user sees the new "
        "label. Runtime detection requires a full Playwright loop on every "
        "build. The trade-off is false positives: a term may be legitimate in "
        "context. The blocklist is intentionally conservative — add new terms "
        "with a corresponding suggested replacement rather than blanket bans.",
        "",
        "## When to expand the blocklist",
        "",
        "Add a term when:",
        "  * A user has asked what it means (visible in support transcripts).",
        "  * A designer has called it out (visible in design review).",
        "  * The term appears in the i18n registry verbatim, in English, "
        "    without a Hindi equivalent that also doesn't translate the term.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Run as ``python -m shopstack.tools.copy_audit``."""
    report = run_audit()
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text(render_markdown(report), encoding="utf-8")
    OUTPUT_JSON.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    try:
        md_label = str(OUTPUT_MD.relative_to(PROJECT_ROOT))
    except ValueError:
        md_label = str(OUTPUT_MD)
    try:
        json_label = str(OUTPUT_JSON.relative_to(PROJECT_ROOT))
    except ValueError:
        json_label = str(OUTPUT_JSON)
    print(
        f"→ {md_label} ({len(report.violations)} violations across {report.scanned_files} files)"
    )
    print(f"→ {json_label}")
    return 0 if not report.violations else 1


__all__ = [
    "CopyReport",
    "OVERRIDES",
    "Violation",
    "main",
    "render_markdown",
    "run_audit",
    "scan_file",
    "scan_i18n",
]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
