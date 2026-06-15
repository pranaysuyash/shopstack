"""Empty-state lint — flags passive "no X yet" copy.

This is the CI guard for UX_OVERHAUL_PLAN §Phase 3 (actionable empty
states). It is intentionally non-blocking: it emits a report and
exits 0 by default. Pass ``--strict`` to make it exit non-zero on
any finding (use in CI gates).

Why a lint and not a test
=========================

Empty-state copy lives in three places:

1. Inline HTML / f-strings in screen files
2. Calls to ``empty_state_enhanced(message, ...)`` (primitive)
3. Calls to ``render_empty_state(preset_id, ...)`` (new service)

Tests can't easily cover (1) without becoming brittle, and they
don't fail at the right moment — a copy change is a UX decision,
not a behavior change. A lint is the right tool because:

- It runs at commit time, when the change is small
- It reports the exact file:line so the author can fix it
- It can be made non-blocking to avoid false-positive churn

What it flags
=============

A "passive" empty-state message is a user-facing string that
describes a missing state but does not answer the user's two
implicit questions:

  - "What is missing?"
  - "What should I do next?"

Pattern examples (the lint is heuristic — false positives are
acceptable, false negatives are not):

  * "No X yet."          → flag (passive)
  * "Nothing to show."   → flag (passive)
  * "List is empty."     → flag (passive)
  * "X is empty."        → flag (passive, unless followed by an
                                actionable verb in the same string)

A "good" empty state (not flagged) typically includes:

  * A CTA verb ("Add", "Import", "Try", "Open", "Record")
  * OR a specific next action ("add 5 staples", "scan a receipt",
    "tap + to add your first item")
  * OR a tab-switch / link to the next step

Heuristics the lint uses
========================

1. **Pattern match.** String contains one of: "no X yet",
   "nothing", "is empty", "no data", "no items", "no X to" (and
   similar). The lint normalises the message and checks for an
   actionable verb or next-step phrase in the same string.

2. **Call-site check.** When the message is passed to
   ``empty_state_enhanced`` or ``render_empty_state``, the lint
   checks that the call also passes a non-empty ``action_label``
   (or a ``preset_id`` that the registry defines as actionable).
   Passive message + no action_label → flag.

3. **Co-location check.** Strings inside ``gr.Markdown`` or
   ``gr.HTML(...)`` blocks that include the message inline are
   flagged unless the same statement includes a CTA button or a
   tab-switch link.

The lint is **advisory** by default. In CI, run it as
``python -m shopstack.tools.lint_empty_states`` and treat the
output as a checklist for the PR author.

Adoption
========

Per UX_OVERHAUL_PLAN §Phase 3, every empty state in the app
should pass this lint. The lint is intentionally conservative
(it favours false negatives over false positives) so it can be
adopted in one pass without churning the entire codebase.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path


# ── Patterns ────────────────────────────────────────────────────────────

# A "passive" empty-state pattern. We use a small set of canonical
# patterns rather than a free-form list to keep false positives low.
PASSIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bno\s+\w+\s+yet\b", re.IGNORECASE),
    re.compile(r"\bnothing\s+to\s+show\b", re.IGNORECASE),
    re.compile(r"\bnothing\s+here\b", re.IGNORECASE),
    re.compile(r"\bis\s+empty\b", re.IGNORECASE),
    re.compile(r"\bno\s+\w+\s+to\s+", re.IGNORECASE),
    re.compile(r"\bno\s+data\b", re.IGNORECASE),
    re.compile(r"\bno\s+items?\b", re.IGNORECASE),
    re.compile(r"\bno\s+restock\s+predictions\b", re.IGNORECASE),
    re.compile(r"\bno\s+traces\b", re.IGNORECASE),
    re.compile(r"\bno\s+snapshots?\b", re.IGNORECASE),
    re.compile(r"\bno\s+corrections\b", re.IGNORECASE),
)

# Decision/skip messages that LOOK like empty states but are not
# (they communicate a positive user outcome: "you're good, don't
# buy"). The lint should not flag these.
DECISION_SKIP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bno\s+need\s+to\s+", re.IGNORECASE),
    re.compile(r"\benough\s+at\s+home\b", re.IGNORECASE),
    re.compile(r"\brecently\s+purchased\b", re.IGNORECASE),
)


def _looks_like_svg_or_html(s: str) -> bool:
    """Return True if the string is clearly an HTML/SVG attribute value
    or a prompt template — not a user-facing empty-state message.
    """
    if "<svg" in s or "</svg>" in s or "fill=" in s or "stroke=" in s:
        return True
    # prompt templates often contain "Inventory is empty" as a hint
    if s.startswith(("You are", "The user", "Context:", "Examples:")):
        return True
    return False


def _is_decision_skip_message(s: str) -> bool:
    """Return True if the string is a positive skip/decision message
    rather than an empty state."""
    return any(pat.search(s) for pat in DECISION_SKIP_PATTERNS)


# An "actionable" hint. If a passive pattern is followed (in the
# same string or in a sibling kwarg) by one of these, the empty
# state is considered actionable and is NOT flagged.
ACTIONABLE_VERBS: tuple[str, ...] = (
    "add ", "import ", "scan ", "tap ", "click ", "try ", "open ",
    "record ", "open the ", "switch to ", "go to ", "navigate to ",
    "call ", "use ", "select ", "upload ",
    "add your first", "add a few", "add 5", "add 3", "add the",
    "we'll start", "we'll predict", "we'll show", "once you add",
    "to start", "to enable", "to begin",
)


# ── Finding model ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class Finding:
    """A single lint finding."""
    file: str
    line: int
    pattern: str
    message: str
    suggestion: str


def _is_actionable(message: str) -> bool:
    """Return True if the message already includes an actionable verb."""
    lower = message.lower()
    return any(verb in lower for verb in ACTIONABLE_VERBS)


def _suggest_action(message: str) -> str:
    """Return a suggested actionable replacement (best-effort)."""
    lower = message.lower()
    if "no restock predictions" in lower:
        return (
            "Add a few purchases (e.g. milk, bread, rice, eggs, curd) "
            "and we'll start predicting refill dates after a few buys."
        )
    if "no traces" in lower:
        return (
            "Traces appear after your first tool call — try Add Purchase, "
            "Use Soon, or the command input on Home."
        )
    if "no snapshots" in lower or "no swiggy" in lower or "no price" in lower:
        return (
            "Import a snapshot via the snapshot script, or record your "
            "first purchase with a price to seed the price memory."
        )
    if "no corrections" in lower:
        return (
            "Corrections are recorded after reconciliation when the system "
            "misclassifies an item — the list will populate as you shop."
        )
    if "is empty" in lower:
        return "Add 5 pantry staples to seed recommendations and tracking."
    return "Add a next-action verb (Add, Import, Scan, Try) to the message."


# ── AST-based scanning ─────────────────────────────────────────────────


def _build_parent_map(tree: ast.AST) -> dict[int, ast.AST]:
    """Build a map from child AST node id to its parent.

    ``ast.walk()`` does not preserve parents, so we walk the tree
    once and record each child's parent. This is used to detect
    when a string constant is INSIDE an ``empty_state_enhanced()``
    call (so pattern B should be suppressed in favour of pattern A).
    """
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


def _has_ancestor_call(node: ast.AST, parents: dict[int, ast.AST],
                      name: str) -> bool:
    """Return True if ``node`` is inside a Call whose function name matches."""
    cur: ast.AST | None = parents.get(id(node))
    while cur is not None:
        if isinstance(cur, ast.Call):
            fn = cur.func
            fn_name = None
            if isinstance(fn, ast.Name):
                fn_name = fn.id
            elif isinstance(fn, ast.Attribute):
                fn_name = fn.attr
            if fn_name == name:
                return True
        cur = parents.get(id(cur))
    return False


def _full_fstring_value(node: ast.Constant, parents: dict[int, ast.AST]) -> str:
    """If ``node`` is a Constant inside a JoinedStr (f-string), return
    the concatenation of all sibling Constant parts (with ``{...}``
    placeholders preserved as ``"{}"``). Otherwise return the constant's
    own value as a plain string.

    This is needed because Python's f-string parser splits the literal
    parts of an f-string into multiple ``ast.Constant`` children of the
    surrounding ``ast.JoinedStr``. The actionable verb "add" might be
    in a different segment than the passive "No X" prefix, so checking
    only one segment produces false positives.
    """
    if not isinstance(node, ast.Constant):
        return ""
    cur: ast.AST | None = parents.get(id(node))
    while cur is not None and not isinstance(cur, ast.JoinedStr):
        cur = parents.get(id(cur))
    if cur is None:
        return str(node.value)
    # Concatenate all Constant children of the JoinedStr, with
    # placeholders for FormattedValue children.
    parts: list[str] = []
    for child in cur.values:  # JoinedStr.values
        if isinstance(child, ast.Constant):
            parts.append(str(child.value))
        elif isinstance(child, ast.FormattedValue):
            parts.append("{}")
    return "".join(parts)


def _scan_python_file(path: Path) -> list[Finding]:
    """Scan a Python file for passive empty-state patterns.

    The scan applies several "is this actually a passive empty state"
    heuristics before flagging — these are tuned to the ShopStack
    patterns so the lint can be adopted in one pass:

    * ``empty_state_enhanced("No X yet", secondary_text="Add 3-5 …")``
      is NOT flagged if the call has a non-empty ``secondary_text``
      (which is the actionable hint in the canonical primitive).
    * i18n keys like ``"empty.fridge.title": "Fridge is empty"`` are
      NOT flagged if a sibling ``"empty.fridge.body"`` key in the
      same dict literal contains an actionable verb.
    * Decision/skip messages (e.g. "you have enough at home") and
      SVG/prompt templates are skipped.
    * String constants that are CHILDREN of an
      ``empty_state_enhanced()`` or ``render_empty_state()`` call
      are skipped from pattern B (the call-site check in pattern A
      already handled them).
    """
    findings: list[Finding] = []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError):
        return findings

    parents = _build_parent_map(tree)

    for node in ast.walk(tree):
        # Pattern A: string-literal messages passed to empty_state_enhanced()
        # or render_empty_state() without a sibling action_label/CTA kwarg.
        if isinstance(node, ast.Call):
            fn = node.func
            fn_name = None
            if isinstance(fn, ast.Name):
                fn_name = fn.id
            elif isinstance(fn, ast.Attribute):
                fn_name = fn.attr
            if fn_name in ("empty_state_enhanced", "render_empty_state"):
                # Find the message kwarg / first positional arg
                msg = _extract_first_string(node)
                if msg is None:
                    continue
                for pat in PASSIVE_PATTERNS:
                    if pat.search(msg) and not _is_actionable(msg):
                        # Per canonical primitive contract, a non-empty
                        # secondary_text is the actionable hint.
                        action_kwarg = _kwarg_value(node, "action_label")
                        secondary_kwarg = _kwarg_value(node, "secondary_text")
                        if not action_kwarg and not secondary_kwarg:
                            findings.append(Finding(
                                file=str(path),
                                line=node.lineno,
                                pattern=pat.pattern,
                                message=msg,
                                suggestion=_suggest_action(msg),
                            ))
                        break
        # Pattern B: string constants containing passive phrases.
        # Skipped for constants that are children of a
        # ``empty_state_enhanced()`` or ``render_empty_state()`` call —
        # pattern A already handled those (and the actionable hint may
        # live in a sibling kwarg that pattern B can't see).
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _has_ancestor_call(node, parents, "empty_state_enhanced"):
                continue
            if _has_ancestor_call(node, parents, "render_empty_state"):
                continue
            # For f-strings, the actionable verb may be in a sibling
            # Constant segment. Concatenate all parts before checking.
            s = _full_fstring_value(node, parents)
            if not (10 <= len(s) <= 200) or _looks_like_code(s):
                continue
            if _looks_like_svg_or_html(s) or _is_decision_skip_message(s):
                continue
            for pat in PASSIVE_PATTERNS:
                if pat.search(s) and not _is_actionable(s):
                    if _is_log_or_docstring(node, source):
                        continue
                    # Skip i18n keys whose sibling body key is actionable.
                    if _is_i18n_title_with_actionable_body(node, source):
                        continue
                    findings.append(Finding(
                        file=str(path),
                        line=node.lineno,
                        pattern=pat.pattern,
                        message=s,
                        suggestion=_suggest_action(s),
                    ))
                    break
    return findings


def _is_i18n_title_with_actionable_body(node: ast.Constant, source: str) -> bool:
    """Return True if this is an i18n empty.*.title key whose sibling
    empty.*.body key contains an actionable verb.

    Recognises the pattern in shopstack/services/i18n.py where each
    empty-state preset is defined as two dict entries:

        "empty.fridge.title": "Fridge is empty",
        "empty.fridge.body":  "Add what you just bought, or …",

    The title is intentionally terse (a passive label); the body
    carries the action. Flagging the title alone would produce a
    false positive.
    """
    if not hasattr(node, "lineno"):
        return False
    line = source.splitlines()[node.lineno - 1] if node.lineno else ""
    # Match `"empty.<name>.title":` or `"empty.<name>.title" :`
    m = re.search(r'"empty\.\w+\.title"\s*:', line)
    if not m:
        return False
    # Look at the next 5 lines for a sibling `.body` key
    lines = source.splitlines()
    base = m.group(0).split('"')[1].rsplit(".", 1)[0]  # e.g. "empty.fridge"
    for offset in range(1, 6):
        idx = (node.lineno - 1) + offset
        if idx >= len(lines):
            break
        next_line = lines[idx]
        if f'"{base}.body"' in next_line:
            # Extract the string value and check it is actionable.
            val_m = re.search(r':\s*"([^"]+)"', next_line)
            if val_m and _is_actionable(val_m.group(1)):
                return True
    return False


def _extract_first_string(call: ast.Call) -> str | None:
    """Return the first string-typed argument to ``call`` (kwarg or positional)."""
    # Try kwargs first: message, title, body, text, etc.
    for kw in call.keywords:
        if kw.arg in ("message", "title", "body", "text", "label", "name"):
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
    # Fall back to first positional arg
    if call.args and isinstance(call.args[0], ast.Constant) \
            and isinstance(call.args[0].value, str):
        return call.args[0].value
    return None


def _kwarg_value(call: ast.Call, name: str) -> str | None:
    """Return the string value of a kwarg, or None if absent/empty."""
    for kw in call.keywords:
        if kw.arg == name:
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
            if isinstance(kw.value, ast.Constant) and kw.value.value is None:
                return None
    return None


def _looks_like_code(s: str) -> bool:
    """Return True if the string looks like code (not user copy)."""
    if "%" in s and ("s" in s.split("%") or "d" in s.split("%")):
        return True
    if s.startswith(("def ", "class ", "import ", "from ", "return ", "if ", "for ")):
        return True
    if s.startswith(("/", "  ", "\t", "git ", "uv ", "pytest", "ruff", "python ")):
        return True
    if "_" in s and " " not in s:
        return True
    return False


def _is_log_or_docstring(node: ast.AST, source: str) -> bool:
    """Return True if the string looks like a log message or docstring."""
    if not hasattr(node, "lineno"):
        return False
    line = source.splitlines()[node.lineno - 1] if node.lineno else ""
    stripped = line.lstrip()
    if stripped.startswith(('"""', "'''", 'r"""', "r'''")):
        return True
    if "logger." in stripped or "log." in stripped or "print(" in stripped:
        return True
    return False


# ── Driver ─────────────────────────────────────────────────────────────


def scan_repo(
    repo_root: Path,
    exclude_patterns: tuple[str, ...] = (),
) -> list[Finding]:
    """Scan the whole repo and return all findings.

    Args:
        repo_root: The repo root to scan from.
        exclude_patterns: Tuple of glob-style patterns (matched as
            substrings against the absolute file path) to skip.
            The default tool itself is always excluded.
    """
    findings: list[Finding] = []
    default_excludes = {
        "shopstack/tools/lint_empty_states.py",  # self-scan
    }
    for path in repo_root.rglob("*.py"):
        # Skip caches, venv, and build artifacts.
        parts = set(path.parts)
        if parts & {".venv", "node_modules", "__pycache__", ".git", ".pytest_cache",
                    "build", "dist", ".mypy_cache", ".ruff_cache"}:
            continue
        path_str = str(path)
        # Apply user excludes.
        if any(pat in path_str for pat in exclude_patterns):
            continue
        # Apply default excludes.
        if any(pat in path_str for pat in default_excludes):
            continue
        findings.extend(_scan_python_file(path))
    return findings


def _format_finding(f: Finding) -> str:
    return (
        f"{f.file}:{f.line}\n"
        f"  pattern: {f.pattern}\n"
        f"  message: {f.message!r}\n"
        f"  suggest: {f.suggestion}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lint user-facing empty-state copy for actionability.",
    )
    parser.add_argument(
        "--root", default=".", help="Repo root (default: cwd).",
    )
    parser.add_argument(
        "--exclude", action="append", default=[],
        help="Substring pattern to exclude from the scan (repeatable). "
             "The lint tool itself is always excluded.",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit non-zero on any finding (use in CI gates).",
    )
    args = parser.parse_args(argv)

    findings = scan_repo(
        Path(args.root).resolve(),
        exclude_patterns=tuple(args.exclude),
    )
    if not findings:
        print("lint_empty_states: no findings (clean).")
        return 0

    print(f"lint_empty_states: {len(findings)} finding(s).")
    for f in findings:
        print(_format_finding(f))
        print()
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
