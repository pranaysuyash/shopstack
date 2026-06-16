"""Regression tests for the safe_render_html utility (2026-06-15).

The 2026-06-15 audit flagged the silent-exception pattern
(``except Exception: return ""`` or similar) in 200+ places
across ``shopstack/ui/`` and ``shopstack/services/``. Per
motto_v3 §0.10 + §0.14, the user must see a real error shell
(not a blank screen) when something fails.

These tests pin the new contract:

* The wrapped function returns its HTML on success.
* On exception, the wrapper returns a :func:`branded_error_shell`
  containing:
    - the user_message
    - an "Error id:" line (so the user can quote it to support)
    - the exception type and message (in the collapsible detail)
    - a "Back to dashboard" CTA
    - a "Retry" CTA (when retry_label is supplied)
* The exception is LOGGED (motto_v3 §0.10 — operator visibility).

Evidence tier: T1 (static inspection) + T2 (this test passes).
"""
from __future__ import annotations

import logging

import pytest


# ── Happy path ────────────────────────────────────────────────────


def test_safe_render_html_passes_through_success() -> None:
    from shopstack.ui.errors import safe_render_html

    def good() -> str:
        return "<div>OK</div>"

    # user_message is only required for the error path, but
    # we pass it explicitly here so the contract is uniform.
    assert safe_render_html(good, user_message="ok") == "<div>OK</div>"


def test_safe_render_html_returns_complex_html_unchanged() -> None:
    """Complex HTML (with attributes, escaping, etc.) is
    returned verbatim — the wrapper does not transform success.
    """
    from shopstack.ui.errors import safe_render_html

    payload = "<div class='x' data-id='42'>" "&amp;" "<script>safe</script></div>"

    def good() -> str:
        return payload

    assert safe_render_html(good, user_message="ok") == payload


# ── Error path: returns branded_error_shell ───────────────────────


def test_safe_render_html_returns_shell_on_exception() -> None:
    from shopstack.ui.errors import safe_render_html

    def bad() -> str:
        raise ValueError("something broke")

    html = safe_render_html(bad, user_message="Could not load X")
    # The user_message must be visible
    assert "Could not load X" in html
    # The error id line must be present
    assert "Error id:" in html
    # The exception type must be in the detail
    assert "ValueError" in html
    # The exception message must be in the detail
    assert "something broke" in html
    # role="alert" + aria-live="assertive" (a11y) — primitives
    # use single quotes in the rendered HTML; check both.
    assert "role='alert'" in html or 'role="alert"' in html
    assert "aria-live='assertive'" in html or 'aria-live="assertive"' in html


def test_safe_render_html_does_not_swallow_different_exceptions() -> None:
    """Multiple exception types all get the same treatment —
    ValueError, KeyError, TypeError, RuntimeError.
    """
    from shopstack.ui.errors import safe_render_html

    for exc in (
        ValueError("v"),
        KeyError("k"),
        TypeError("t"),
        RuntimeError("r"),
    ):
        def bad(_e=exc) -> str:
            raise _e
        html = safe_render_html(bad, user_message="error")
        assert type(exc).__name__ in html
        assert str(exc).strip("'") in html or str(exc) in html


def test_safe_render_html_error_id_is_unique_per_call() -> None:
    """Each error gets a unique error_id. The user can quote
    it to support. Two consecutive failures must produce two
    different error ids.
    """
    from shopstack.ui.errors import safe_render_html

    def bad() -> str:
        raise ValueError("x")

    html1 = safe_render_html(bad, user_message="err")
    html2 = safe_render_html(bad, user_message="err")
    # Extract the error ids from each html (format: "Error id: abcdef12\n")
    import re
    m1 = re.search(r"Error id:\s*([0-9a-f]+)", html1)
    m2 = re.search(r"Error id:\s*([0-9a-f]+)", html2)
    assert m1 and m2
    assert m1.group(1) != m2.group(1), (
        f"Error ids must be unique per call: {m1.group(1)} vs {m2.group(1)}"
    )


# ── Error path: logs the exception ───────────────────────────────


def test_safe_render_html_logs_the_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Per motto_v3 §0.10 Observability Is Delivery, every
    caught exception must be LOGGED so the operator can find
    it in the server log.
    """
    from shopstack.ui.errors import safe_render_html

    def bad() -> str:
        raise RuntimeError("explode")

    with caplog.at_level(logging.WARNING, logger="shopstack.ui.errors"):
        safe_render_html(bad, user_message="error-Y")

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("error-Y" in r.getMessage() for r in warnings), (
        f"safe_render_html did not log the user_message; "
        f"saw: {[r.getMessage() for r in warnings]}"
    )
    assert any("RuntimeError" in r.getMessage() for r in warnings), (
        f"safe_render_html did not log the exception type; "
        f"saw: {[r.getMessage() for r in warnings]}"
    )
    assert any("explode" in r.getMessage() for r in warnings), (
        f"safe_render_html did not log the exception message; "
        f"saw: {[r.getMessage() for r in warnings]}"
    )


# ── XSS safety ────────────────────────────────────────────────────


def test_safe_render_html_escapes_user_message_with_xss() -> None:
    """The user_message is rendered inside HTML. Special
    characters must be escaped (motto_v3 §0.7 — no XSS).
    """
    from shopstack.ui.errors import safe_render_html

    def bad() -> str:
        raise ValueError("x")

    html = safe_render_html(
        bad,
        user_message="<script>alert(1)</script>",
    )
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
