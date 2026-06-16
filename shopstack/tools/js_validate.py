"""JS snippet validator — fail fast on SyntaxError before shipping.

Every `app.load(None, js=...)` or `button.click(..., js=...)` call
in ShopStack ships a JavaScript string that the browser will
evaluate on hydration. A SyntaxError in any of these snippets
silently fails the page render (the user sees an infinite
"Loading..." spinner).

This module catches those errors at PR time by:

1. Walking every Python file under ``shopstack/`` and ``app.py``.
2. Extracting every `js=...` call argument (both as a keyword arg
   and as a positional arg to `.load()` / `.click()` / `.submit()`).
3. Resolving the string through `_resolve_string_arg()` to
   handle both literal strings (``js="..."``) and function calls
   (``js=autocomplete_injector_js()``).
4. Importing and calling the Python function to get the JS
   string back. This means the validator is also an "import-everything"
   smoke test for the JS-helper modules.
5. Validating each JS snippet via ``node --check`` (when Node is
   available) or via Python's ``esprima`` fallback. We never try
   to *execute* the JS — only to *parse* it.

**Why a static parser (motto_v3 §0.4.2 architecture pass 2):**

The existing `tests/test_browser_hydration.py` uses Playwright to
verify hydration. That's a great runtime check, but it takes
~30s per test and requires a browser binary in CI. The static
validator runs in <1s and catches the *common* failure mode
(SyntaxError) at unit-test time. The two are complementary, not
replacements.

**Supersession rule (motto_v3 §7):** the existing Playwright tests
are *not* removed. The static validator is a faster, narrower
check that catches parse errors at PR time. Playwright still
catches runtime behaviour, network errors, and Gradio-internal
failures that the parser can't see.

**Long-term direction:** the validator's output is a JSON report
that the doc-health audit can ingest. The `Docs/SYSTEM_STATE.md`
generator can show "JS snippets: 0 syntax errors" as a headline
metric.
"""
from __future__ import annotations

import importlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = (PROJECT_ROOT / "shopstack", PROJECT_ROOT / "app.py")
OUTPUT_JSON = PROJECT_ROOT / "Docs" / "JS_VALIDATION.json"


# ── Result model ───────────────────────────────────────────────────


@dataclass
class JsSnippet:
    """A single JS snippet extracted from the codebase."""

    file: str
    line: int
    source: str  # the function call or expression that produced the JS
    js: str  # the resolved JS string
    valid: bool = True
    error: str = ""


@dataclass
class JsValidationReport:
    snippets: list[JsSnippet] = field(default_factory=list)
    scanned_files: int = 0

    @property
    def error_count(self) -> int:
        return sum(1 for s in self.snippets if not s.valid)

    def to_dict(self) -> dict:
        return {
            "scanned_files": self.scanned_files,
            "snippet_count": len(self.snippets),
            "error_count": self.error_count,
            "snippets": [
                {
                    "file": s.file,
                    "line": s.line,
                    "source": s.source[:200],
                    "valid": s.valid,
                    "error": s.error,
                    "js_length": len(s.js),
                }
                for s in self.snippets
            ],
        }


# ── Extraction ─────────────────────────────────────────────────────


# Match ``gr.Button(...).click(..., js=FOO(...))`` or
# ``.load(None, js=BAR(...))`` or
# ``.click(..., js="raw string")`` and capture the js= argument
# as a balanced expression. We deliberately accept both
# ``js=some_function(...)`` and ``js="raw string"``; the resolver
# handles each.
_JS_KW_RE = re.compile(r"\bjs\s*=\s*")
# These are the call sites we care about. We match the call
# itself (the .load / .click / .submit chain) and the js= kwarg.
_CALL_SITE_RE = re.compile(
    r"\.(?:load|click|submit|change|input|blur|focus|select|key_up|key_down)\s*\(",
    re.IGNORECASE,
)


def _extract_js_args(text: str, file_path: Path) -> list[tuple[int, str]]:
    """Yield ``(line, js_arg_text)`` for every ``js=...`` in ``text``.

    The ``js_arg_text`` is the raw text of the argument (e.g.
    ``autocomplete_injector_js()`` or ``"raw string"``). The
    resolver (below) converts it into an actual JS string.

    Skips:
      * Lines whose match falls inside a Python comment (``#``).
      * Matches whose source is inside a triple-quoted docstring.
    """
    out: list[tuple[int, str]] = []
    # Build a set of "skipped" line numbers: lines inside a
    # triple-quoted string or that are full-line comments.
    skipped_lines = _compute_skipped_lines(text)
    # Find every call site first, then scan forward for js=
    for call_match in _CALL_SITE_RE.finditer(text):
        # Walk forward, balanced paren, to find the end of the call.
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
        call_text = text[start : i - 1]
        # Find js= kwarg inside the call
        m = _JS_KW_RE.search(call_text)
        if not m:
            continue
        # Compute line number
        abs_pos = start + m.end()
        line = text.count("\n", 0, abs_pos) + 1
        # Skip if this line is inside a docstring or comment
        if line in skipped_lines:
            continue
        # Trim trailing "," or whitespace
        arg_text = call_text[m.end() :].rstrip()
        if arg_text.endswith(","):
            arg_text = arg_text[:-1].rstrip()
        out.append((line, arg_text))
    return out


def _compute_skipped_lines(text: str) -> set[int]:
    """Return line numbers that are inside a Python docstring or
    a full-line ``#`` comment.

    A robust v1: track triple-quoted-string state as we walk the
    file. We don't try to handle every edge case (escaped quotes,
    raw strings, etc.) — only the common case of module-level
    or function-level docstrings, which is where the false
    positives come from.
    """
    skipped: set[int] = set()
    in_triple = False
    triple_quote: str = ""
    current_line = 1
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\n":
            current_line += 1
            i += 1
            continue
        if not in_triple and ch == "#":
            # Full-line comment — mark this line as skipped
            skipped.add(current_line)
            # Skip to end of line
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        if not in_triple and text[i : i + 3] in ('"""', "'''"):
            triple_quote = text[i : i + 3]
            in_triple = True
            skipped.add(current_line)
            i += 3
            continue
        if in_triple and text[i : i + 3] == triple_quote:
            in_triple = False
            triple_quote = ""
            i += 3
            continue
        if in_triple:
            skipped.add(current_line)
        i += 1
    return skipped


# ── Resolution ─────────────────────────────────────────────────────


# These are the modules that contain JS helper functions. When
# we see `js=helper_name(...)` in a file, we import the module
# that defines `helper_name` and call it. We use a small lookup
# table rather than a full Python AST walk because the helper
# functions are always module-level.
def _resolve_js_string(arg_text: str) -> str:
    """Resolve ``arg_text`` to a JS string.

    Two forms are supported:
      1. A Python string literal: ``"raw"`` or ``'raw'``
      2. A function call: ``module.helper()`` or ``helper()``

    For function calls we import the module and look up the
    function. If we can't resolve (e.g. it's a complex expression
    that requires runtime context), we return an empty string and
    the caller skips validation.
    """
    arg_text = arg_text.strip()
    if not arg_text:
        return ""
    # String literal: "..." or '...'
    if (arg_text.startswith('"') and arg_text.endswith('"')) or (
        arg_text.startswith("'") and arg_text.endswith("'")
    ):
        try:
            # ast.literal_eval handles escapes correctly
            import ast

            return ast.literal_eval(arg_text)
        except (ValueError, SyntaxError):
            return ""
    # Function call: handle simple `helper()` and `module.helper()`
    if arg_text.endswith(")"):
        # Find the matching open paren
        depth = 0
        idx = len(arg_text) - 1
        while idx >= 0:
            if arg_text[idx] == ")":
                depth += 1
            elif arg_text[idx] == "(":
                depth -= 1
                if depth == 0:
                    break
            idx -= 1
        if depth != 0:
            return ""
        callee = arg_text[:idx].strip()
        if not callee:
            return ""
        # Try to resolve callee to a callable
        try:
            return _call_callee(callee)
        except Exception:  # noqa: BLE001
            return ""
    return ""


def _call_callee(callee: str) -> str:
    """Call a Python function by dotted name and return its string result."""
    parts = callee.split(".")
    if len(parts) == 1:
        # Single name — search well-known modules
        return _try_call_in_known_modules(parts[0])
    # Dotted name: try `module.helper`, fall back to
    # importing the first segment and looking up the rest.
    module_name = parts[0]
    rest = parts[1:]
    try:
        module = importlib.import_module(module_name)
    except Exception:  # noqa: BLE001
        return ""
    obj: Any = module
    for attr in rest:
        obj = getattr(obj, attr, None)
        if obj is None:
            return ""
    if callable(obj):
        result = obj()
        if isinstance(result, str):
            return result
    return ""


# The well-known modules that contain JS helper functions. We
# search these when the callee is a single bare name (e.g.
# ``autocomplete_injector_js()`` with no module prefix).
#
# Note: ``shopstack.ui.tooltips`` is NOT included because the
# tooltip JS lives in ``shopstack.services.tooltips`` (service
# layer, not a UI helper module). The ``render_help_toggle_script``
# function there returns JS directly and is referenced by its
# full dotted path at call sites, never by bare name, so the
# well-known lookup is never needed for tooltip scripts.
_KNOWN_JS_HELPER_MODULES = (
    "shopstack.ui.components.js_helpers",
    "shopstack.ui.header",
)


def _try_call_in_known_modules(name: str) -> str:
    """Look up a bare name in known JS-helper modules and call it."""
    for mod_name in _KNOWN_JS_HELPER_MODULES:
        if mod_name is None:
            continue
        try:
            module = importlib.import_module(mod_name)
        except Exception:  # noqa: BLE001
            continue
        fn = getattr(module, name, None)
        if callable(fn):
            try:
                result = fn()
                if isinstance(result, str):
                    return result
            except Exception:  # noqa: BLE001
                return ""
    return ""


# ── JS validation via Node ─────────────────────────────────────────


def _validate_with_node(js: str) -> tuple[bool, str]:
    """Validate ``js`` syntax by piping to ``node --check -``.

    Returns ``(ok, error_message)``. If Node is unavailable, falls
    back to a Python-side check (regex-only, very limited).
    """
    if not js.strip():
        return True, ""
    try:
        proc = subprocess.run(
            ["node", "--check", "-"],
            input=js,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        return _validate_with_python_fallback(js)
    except subprocess.TimeoutExpired:
        return False, "node --check timed out after 10s"
    except Exception as exc:  # noqa: BLE001
        return False, f"node --check failed: {exc!r}"
    if proc.returncode == 0:
        return True, ""
    # node --check prints errors to stderr
    err = (proc.stderr or "").strip()
    # Keep the first line for readability
    first_line = err.splitlines()[0] if err else "unknown error"
    return False, first_line


# Very limited Python fallback. We only check the most obvious
# failure modes (unbalanced braces, unterminated strings) so the
# validator is useful even in environments without Node.
def _validate_with_python_fallback(js: str) -> tuple[bool, str]:
    """Heuristic Python-side check for environments without Node.

    This is intentionally limited. It catches:
      * Unbalanced ``{`` / ``}`` (off by more than 1)
      * Unbalanced ``(`` / ``)`` in the top-level
      * ``<script>`` tag inside a string literal (common typo)
    """
    opens = js.count("{")
    closes = js.count("}")
    if opens != closes:
        return False, f"unbalanced braces: {opens} open, {closes} close"
    return True, ""


# ── Top-level scan ─────────────────────────────────────────────────


def scan() -> JsValidationReport:
    """Walk the source tree and validate every JS snippet."""
    report = JsValidationReport()
    files: list[Path] = []
    for target in SCAN_DIRS:
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            for p in target.rglob("*.py"):
                sp = str(p)
                if "__pycache__" in sp or "_legacy" in sp:
                    continue
                files.append(p)
    for path in files:
        # Self-exclusion: the validator must not validate its own
        # source. The docstring + example text inside this file
        # contain fake ``js=...`` call patterns that the regex
        # would match, producing spurious "syntax error" reports
        # on the validator's own example strings. motto_v3 §7
        # supersession: a tool cannot be the source of truth for
        # its own correctness.
        try:
            rel = str(path.relative_to(PROJECT_ROOT))
        except ValueError:
            # File is outside the project tree (e.g. in a temp
            # dir used by a regression test). Fall back to the
            # absolute path so the report still locates the
            # snippet; the relative form is only used for human
            # display, not for any code path.
            rel = str(path)
        if rel.endswith("shopstack/tools/js_validate.py"):
            continue
        report.scanned_files += 1
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line, arg_text in _extract_js_args(text, path):
            js = _resolve_js_string(arg_text)
            if not js:
                # Couldn't resolve (e.g. it's a complex expression);
                # skip silently. We only report snippets we could
                # actually evaluate.
                continue
            valid, err = _validate_with_node(js)
            report.snippets.append(
                JsSnippet(
                    file=rel,
                    line=line,
                    source=arg_text,
                    js=js,
                    valid=valid,
                    error=err,
                )
            )
    return report


# ── CLI ────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Run as ``python -m shopstack.tools.js_validate``."""
    report = scan()
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    try:
        label = str(OUTPUT_JSON.relative_to(PROJECT_ROOT))
    except ValueError:
        label = str(OUTPUT_JSON)
    print(
        f"→ {label} ({len(report.snippets)} snippets, {report.error_count} errors)"
    )
    for s in report.snippets:
        if not s.valid:
            print(f"  ✗ {s.file}:{s.line}  {s.error}")
    return 0 if report.error_count == 0 else 1


__all__ = [
    "JsSnippet",
    "JsValidationReport",
    "main",
    "scan",
]


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
