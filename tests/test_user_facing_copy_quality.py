"""Regression tests for end-user-facing copy quality (2026-06-15).

Per `motto_v3` §0.14 (Product Reality and Operator Workflow Rule) and
the 2026-06-14 copy-standards audit (the ``shopstack/tools/copy_audit.py``
blocklist + the consumer copy audit workflow), every message shown to
a real user must be:

  1. End-user-readable — no engineering jargon (no "stack trace",
     "database error", "exception", raw Python repr, internal class
     names).
  2. End-user-actionable — when something failed, the user knows
     what they can do (retry, refresh, contact support).
  3. Reassuring when appropriate — for data-loss-risk scenarios, the
     message must tell the user their data is safe.

The pre-2026-06-15 app violated rule #1 in at least two places:

  - ``shopstack/ui/tabs/command_surface.py`` exposed raw exception
    text in user-facing toasts (``f"Could not add: {exc}"``,
    ``f"Could not log: {exc}"``, ``f"Could not mark: {exc}"``,
    ``f"Could not answer: {exc}"``, and the dispatcher
    ``f"Something went wrong: {exc}"``). A user with a transient
    DB error would see a Python traceback fragment in their
    shopping-list toast. Unacceptable.
  - ``shopstack/ui/views.py::ERROR_HTML`` printed "Could not load
    price history due to a database error." in red text. The
    phrase "database error" is internal jargon; the user does
    not care *why* the load failed, they care *what they can do
    next*.

This test enforces the rule for the two files in the blast
radius of the 2026-06-15 fix. The static pattern (regex on the
source file) is a deliberately broad guard — it catches not just
the specific patterns I fixed but any future regression of the
same class.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMMAND_SURFACE = ROOT / "shopstack" / "ui" / "tabs" / "command_surface.py"
SERVICES_COMMAND_SURFACE = ROOT / "shopstack" / "services" / "command_surface.py"
VIEWS = ROOT / "shopstack" / "ui" / "views.py"
HOME_FLOW = ROOT / "shopstack" / "services" / "home_flow.py"


# Jargon tokens that must never appear in a user-facing string.
# Each entry is a (token, why-it-is-bad) pair; the test fails if
# any token appears inside a ``message=`` / ``headline=`` /
# ``subhead=`` argument in the guarded file.
JARGON_TOKENS: list[tuple[str, str]] = [
    (r"\bstack ?trace\b", "engineering jargon"),
    (r"\btraceback\b", "engineering jargon"),
    (r"\bexception\b", "engineering jargon"),
    (r"\b\d+\.\d+\.\d+\b", "looks like a version number"),
    (r"<class '[^']+'>", "Python class repr (str(exc) format)"),
    (r"\bmodule '[^']+' has no attribute\b", "raw AttributeError text"),
    (r"\bkey error\b", "internal KeyError exposed"),
    (r"\battribute error\b", "internal AttributeError exposed"),
    (r"\btype error\b", "internal TypeError exposed"),
    (r"\b\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", "raw timestamp leaked"),
]


# Phrases that must not appear in the headline/subhead of a
# user-facing state.
HEADLINE_JARGON: list[tuple[str, str]] = [
    (r"\bhome state\b", "jargon — 'home state' is internal state-machine name"),
    (r"\bdatabase\b", "jargon — user does not care about the DB"),
    (r"\bserver log", "operator language — 'server logs'"),
    (r"\bserver log\b", "operator language — 'server log'"),
    (r"\bSQLite\b", "internal database engine name"),
    (r"\bpostgresql\b", "internal database engine name"),
    (r"\bSQL\b", "internal query language"),
    (r"\bstack ?trace\b", "engineering jargon"),
    (r"\btraceback\b", "engineering jargon"),
]


# ── command_surface.py: handler error messages ──────────────────────


def _find_user_facing_message_strings(path: Path) -> list[tuple[int, str]]:
    """Find every literal passed as a `message=` argument in *path*.

    Returns a list of (line_number, message_value) tuples. The
    regex is conservative: it matches ``message="..."`` or
    ``message='...'` and ``message=f"..."`` patterns. For
    f-strings, the literal text is extracted (interpolations are
    flagged separately).
    """
    text = path.read_text()
    results: list[tuple[int, str]] = []
    # Match message= followed by a string literal.
    pattern = re.compile(
        r"""message\s*=\s*(?P<q>['"])(?P<val>(?:\\.|(?!(?P=q)).)*)(?P=q)"""
    )
    for m in pattern.finditer(text):
        line = text[: m.start()].count("\n") + 1
        results.append((line, m.group("val")))
    return results


@pytest.mark.parametrize(
    "path",
    [COMMAND_SURFACE, SERVICES_COMMAND_SURFACE],
    ids=["ui/tabs/command_surface.py", "services/command_surface.py"],
)
def test_command_surface_error_messages_have_no_jargon(path: Path) -> None:
    """Every `message=` literal in command_surface must be jargon-free.

    2026-06-15 regression guard: the pre-fix code passed raw
    ``str(exc)`` to users in failure toasts. The new messages
    say "Please try again" and name the action that failed.
    """
    for line, msg in _find_user_facing_message_strings(path):
        assert msg, f"Empty message literal at {path.name}:{line}"
        for pattern, why in JARGON_TOKENS:
            assert not re.search(pattern, msg, re.IGNORECASE), (
                f"User-facing message at {path.name}:{line} contains "
                f"jargon (matched {pattern!r}: {why}). "
                f"Message: {msg!r}. Per motto_v3 §0.14, the user must "
                f"see actionable end-user copy, not raw engineering "
                f"output. Log the technical detail at error level; "
                f"the message should be plain English."
            )


@pytest.mark.parametrize(
    "path",
    [COMMAND_SURFACE, SERVICES_COMMAND_SURFACE],
    ids=["ui/tabs/command_surface.py", "services/command_surface.py"],
)
def test_command_surface_error_messages_name_a_recovery_action(path: Path) -> None:
    """Every UNEXPECTED failure `message=` must end with a recovery hint.

    End-user copy standard (motto_v3 §0.14): a failure message
    without an actionable next step leaves the user stuck. The
    canonical recovery hint is "Please try again." — short,
    unambiguous, and works for any failure mode.

    Note: validation messages (e.g. "Item name is required.")
    are a different category — they tell the user what valid
    input looks like, which IS the recovery hint. The test
    excludes those by pattern.
    """
    for line, msg in _find_user_facing_message_strings(path):
        # Only check UNEXPECTED failure messages — "Something went
        # wrong" or "Could not <verb>". Validation messages
        # ("Item name is required.", "No active stock of X to consume.")
        # are excluded because their message itself is the action
        # hint ("provide an item name", "restock X").
        is_unexpected_failure = bool(
            re.match(
                r"^(Could not|Couldn't|Something went|No handler)",
                msg,
            )
        )
        if not is_unexpected_failure:
            continue
        # Unexpected failures must tell the user what to do next.
        assert "please try again" in msg.lower() or "refresh" in msg.lower(), (
            f"Unexpected failure message at {path.name}:{line} does not "
            f"include a recovery hint ('Please try again' or 'refresh'). "
            f"Message: {msg!r}. Per motto_v3 §0.14, a failure without "
            f"a recovery action leaves the user stuck."
        )


def test_command_surface_does_not_interpolate_exc_into_user_message() -> None:
    """No `message=f"... {exc} ..."` patterns in user-facing toasts.

    The pre-2026-06-15 bug was: every handler's except block did
    ``message=f"Could not add: {exc}"``. This is the exact
    pattern that leaked the traceback. The post-fix code uses
    plain strings with a recovery hint; the exception is logged
    at ``error`` level with ``exc_info=True`` for operators.

    This test scans for the interpolation pattern itself, so any
    future handler that re-introduces it fails fast.
    """
    for path in (COMMAND_SURFACE, SERVICES_COMMAND_SURFACE):
        text = path.read_text()
        # Match `message=f"...{exc}..."` or `message=f"...{e}..."`
        # where the interpolation is the exception variable.
        bad = re.findall(
            r"""message\s*=\s*f["'][^"']*\{(?:exc|e|err|error|exception)\b[^"']*\}""",
            text,
        )
        assert not bad, (
            f"{path.name} still interpolates an exception into a "
            f"user-facing message. The exception must go to the log "
            f"(logger.warning/exc_info=True), not the toast. "
            f"Found {len(bad)} occurrences."
        )


# ── views.py: ERROR_HTML constant must not return ──────────────────


def _strip_python_comments_and_docstrings(text: str) -> str:
    """Return *text* with comments and docstrings removed.

    Static copy-quality tests need to scan code (not docs), so
    we strip:
      - line comments starting with ``#`` (outside strings)
      - triple-quoted module/class/function docstrings
    This is a deliberately loose stripper; it does not need to
    be a full Python tokenizer because the test is just a guard
    against hard-coded jargon literals, not a syntax check.
    """
    # Remove triple-quoted strings (docstrings + multi-line strings).
    cleaned = re.sub(r'"""[\s\S]*?"""', '""', text)
    cleaned = re.sub(r"'''[\s\S]*?'''", "''", cleaned)
    # Remove line comments — naive: split into lines, strip after first #.
    out_lines: list[str] = []
    for line in cleaned.splitlines():
        # Naively strip "# " outside of strings. A proper tokenizer
        # is out of scope; this is a heuristic that handles the
        # common "comment at end of line" case.
        in_string = False
        for i, ch in enumerate(line):
            if ch in ('"', "'"):
                in_string = not in_string
            elif ch == "#" and not in_string:
                line = line[:i]
                break
        out_lines.append(line)
    return "\n".join(out_lines)


def test_views_no_legacy_error_html_constant() -> None:
    """The legacy `ERROR_HTML` constant with raw-jargon copy is dead.

    Pre-2026-06-15: ``views.py::ERROR_HTML`` printed "Could not
    load price history due to a database error." in red. It was
    never imported anywhere (dead code per motto_v3 §7) AND it
    used internal jargon ("database error") contradicting
    §0.14. The 2026-06-15 cleanup removed the constant. This
    test guards against re-introduction.
    """
    code = _strip_python_comments_and_docstrings(VIEWS.read_text())
    assert "ERROR_HTML" not in code, (
        f"{VIEWS.name} defines ERROR_HTML in code. The legacy constant "
        f"was removed on 2026-06-15 (per motto_v3 §7 — dead code, plus "
        f"it leaked 'database error' jargon to the end user, violating "
        f"§0.14). Use _recovery_shell(message=..., exc=...) or "
        f"branded_error_shell(...) instead."
    )


def test_views_no_database_error_string_literal() -> None:
    """The string "database error" must not appear as a user-facing literal.

    The pre-2026-06-15 ERROR_HTML constant had it. Belt-and-suspenders
    guard: even if a new constant is introduced, this string in a
    user-facing HTML literal is a copy violation. Comments are
    excluded so historical context in docstrings doesn't trip the
    test.
    """
    code = _strip_python_comments_and_docstrings(VIEWS.read_text())
    assert "database error" not in code.lower(), (
        f"{VIEWS.name} contains the string 'database error' in code. "
        f"The canonical error pattern is _recovery_shell() with a "
        f"plain-English message. 'database error' is internal jargon."
    )


# ── home_flow.py: ERROR state copy must be jargon-free ───────────


def test_home_flow_error_state_headline_is_user_friendly() -> None:
    """The HomeState.ERROR headline must be jargon-free."""
    text = HOME_FLOW.read_text()
    m = re.search(
        r'state=HomeState\.ERROR,\s*headline=(?P<q>["\'])(?P<hl>.*?)(?P=q),\s*subhead=(?P<q2>["\']|\()(?P<sh>.*?)(?:(?P=q2)|\))',
        text,
        re.DOTALL,
    )
    assert m, (
        "Could not find the HomeState.ERROR headline/subhead in home_flow.py. "
        "If you restructured the function, update this test."
    )
    headline = m.group("hl")
    subhead = m.group("sh")
    for label, value in (("headline", headline), ("subhead", subhead)):
        for pattern, why in HEADLINE_JARGON:
            assert not re.search(pattern, value, re.IGNORECASE), (
                f"HomeState.ERROR {label} contains jargon (matched "
                f"{pattern!r}: {why}). Value: {value!r}"
            )


def test_home_flow_error_state_subhead_tells_user_data_is_safe() -> None:
    """The HomeState.ERROR subhead must reassure: data is safe.

    A returning user with 200 items hitting a data error would
    panic ("did I lose everything?"). The error message must
    answer that fear explicitly.
    """
    text = HOME_FLOW.read_text()
    m = re.search(
        r'state=HomeState\.ERROR,\s*headline=(?P<q>["\'])(?P<hl>.*?)(?P=q),\s*subhead=(?P<q2>["\']|\()(?P<sh>.*?)(?:(?P=q2)|\))',
        text,
        re.DOTALL,
    )
    subhead = m.group("sh").lower()
    assert "safe" in subhead, (
        f"HomeState.ERROR subhead does not reassure the user that "
        f"their data is safe. A returning user hitting a data error "
        f"panics ('did I lose everything?'); the message must answer "
        f"that fear. Subhead: {subhead!r}"
    )


def test_home_flow_error_state_offers_a_recovery_action() -> None:
    """The HomeState.ERROR subhead must include a recovery action."""
    text = HOME_FLOW.read_text()
    m = re.search(
        r'state=HomeState\.ERROR,\s*headline=(?P<q>["\'])(?P<hl>.*?)(?P=q),\s*subhead=(?P<q2>["\']|\()(?P<sh>.*?)(?:(?P=q2)|\))',
        text,
        re.DOTALL,
    )
    subhead = m.group("sh").lower()
    has_action = any(
        token in subhead
        for token in ("refresh", "try again", "try the", "check back")
    )
    assert has_action, (
        f"HomeState.ERROR subhead does not offer a recovery action. "
        f"Per motto_v3 §0.14, a failure without a recovery action "
        f"leaves the user stuck. Subhead: {subhead!r}"
    )
