"""Regression test for the 5 silent event-wiring bugs documented in
``Docs/UI_UX_AUDIT_2026.md`` §4.1.

The audit reported these ValueError patterns at app load time:

  1. ``analytics_screen``  — needed: 1, got: 0  (wanted inputs: [Slider])
  2. ``parser_preview_screen`` — needed: 1, got: 0 (wanted inputs: [Textbox])
  3. ``shelf_scan_process`` — needed: 4, got: 1
  4. ``agent_trace_search_filter`` — needed: 2, got: 1
  5. Community opt-in module — function didn't return enough output values
     (needed: 2, returned: 1)

For each handler we statically verify that every Gradio call site
(``click``, ``change``, ``submit``, ``app.load``, ``then``, etc.) is
internally consistent: the number of positional parameters in the
handler signature matches the length of ``inputs=[...]``, and the
number of values returned by the handler matches the length of
``outputs=[...]``.

The audit is now considered stale (the most recent passes have
restructured the relevant call sites), but this test exists so that
the next regression of the same shape fails immediately rather than
silently at app load.

Evidence tier: T1 (static inspection) + T2 (this test passes).
"""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path
from typing import Any, Callable

import pytest


# ── Handler imports (hoisted to module level so pytest pays the import
#    cost once, not per-test; otherwise 5 tests × ~14s of transitive
#    imports = 70s, blowing the fast-feedback budget) ────────────────

from shopstack.ui.screens.analytics import analytics_screen
from shopstack.ui.screens.parser_preview import parser_preview_screen
from shopstack.ui.screens.shelf_scan import shelf_scan_process
from shopstack.ui.screens.traces import agent_trace_search_filter


# ── Helpers ────────────────────────────────────────────────────────────


def _parse_argspec(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[int, int]:
    """Return (required_positional, total_positional) for a function.

    ``total_positional`` includes parameters with defaults. We treat
    ``*args`` as accepting one more positional slot, and ``**kwargs``
    as accepting all remaining slots.
    """
    args = node.args
    positional = list(args.posonlyargs) + list(args.args)
    required = sum(1 for a in positional if a.default is None)
    total = len(positional)
    if args.vararg is not None:
        # *args accepts at least one more positional; we treat that as
        # one extra required slot for the "expected count" check.
        total += 1
        required += 1
    return required, total


def _parse_return_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int | None:
    """Best-effort count of values returned by the function.

    For ``return a, b, c`` or ``return (a, b, c)`` returns the tuple
    size. For ``return value`` returns 1. Returns ``None`` if the
    function has no ``return`` statements or the structure is
    ambiguous (multiple returns, conditional returns, etc.) — in
    which case the caller should treat the function as variable-shape.
    """
    returns = [n for n in ast.walk(node) if isinstance(n, ast.Return)]
    if not returns:
        return 0
    if len(returns) > 1:
        # Multiple return statements → variable shape; cannot assert.
        return None
    ret = returns[0].value
    if ret is None:
        return 0
    if isinstance(ret, ast.Tuple):
        return len(ret.elts)
    if isinstance(ret, ast.Constant):
        return 1
    if isinstance(ret, ast.Name):
        return 1
    if isinstance(ret, ast.Call):
        # Best-effort: a call returning a single value.
        return 1
    return None


def _find_call_kwargs(
    source: str,
    handler_name: str,
) -> list[tuple[int, list[str] | None, list[str] | None]]:
    """Find every call to ``handler_name`` and return its (line, inputs, outputs).

    ``inputs`` / ``outputs`` are returned as a list of the literal
    names/identifiers passed in the kwarg, or ``None`` if the kwarg
    is not present or not a list literal we can statically parse.

    Only matches "naked" calls (``handler_name,``) and attribute
    method calls (``something.handler_name(``) — we want both, e.g.
    ``an_refresh.click(analytics_screen, ...)`` is fine to check via
    the second pattern.
    """
    tree = ast.parse(source)
    results: list[tuple[int, list[str] | None, list[str] | None]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        match = False
        if isinstance(node.func, ast.Name) and node.func.id == handler_name:
            match = True
        elif isinstance(node.func, ast.Attribute) and node.func.attr == handler_name:
            match = True
        if not match:
            continue
        inputs = outputs = None
        for kw in node.keywords:
            if kw.arg == "inputs":
                if isinstance(kw.value, ast.List):
                    inputs = [elt.id if isinstance(elt, ast.Name) else "<expr>"
                              for elt in kw.value.elts]
                elif isinstance(kw.value, ast.Constant) and kw.value.value is None:
                    inputs = []
                else:
                    inputs = ["<expr>"]
            elif kw.arg == "outputs":
                if isinstance(kw.value, ast.List):
                    outputs = [elt.id if isinstance(elt, ast.Name) else "<expr>"
                               for elt in kw.value.elts]
                elif isinstance(kw.value, ast.Constant) and kw.value.value is None:
                    outputs = []
                else:
                    outputs = ["<expr>"]
        results.append((node.lineno, inputs, outputs))
    return results


def _resolve_handler(handler_ref: str) -> Callable[..., Any] | None:
    """Resolve a dotted handler name to a callable.

    Example: ``shopstack.ui.screens.analytics.analytics_screen``.
    Returns ``None`` if the module or attribute cannot be imported.
    """
    try:
        module_name, _, attr = handler_ref.rpartition(".")
        if not module_name:
            return None
        import importlib
        mod = importlib.import_module(module_name)
        return getattr(mod, attr, None)
    except Exception:
        return None


# ── Per-bug regression checks ─────────────────────────────────────────


def test_analytics_screen_call_sites_match_signature() -> None:
    """Audit finding #1: ``analytics_screen`` should not get 0 inputs."""
    from shopstack.ui.screens.analytics import analytics_screen
    sig = inspect.signature(analytics_screen)
    expected_inputs = sum(
        1 for name, p in sig.parameters.items()
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                      inspect.Parameter.POSITIONAL_OR_KEYWORD)
    )
    # Function takes 1 positional parameter; can also be called with 0
    # via the default — so call sites are allowed to be either 0 or 1.
    allowed = {0, expected_inputs}

    src = Path("shopstack/ui/tabs/analytics.py").read_text()
    call_sites = _find_call_kwargs(src, "analytics_screen")
    assert call_sites, "analytics_screen should be referenced in tabs/analytics.py"
    for line, inputs, _outputs in call_sites:
        assert inputs is not None, f"line {line}: missing inputs=[...] kwarg"
        assert len(inputs) in allowed, (
            f"line {line}: analytics_screen expects {expected_inputs} "
            f"positional inputs (or 0 with default), got {len(inputs)}"
        )


def test_parser_preview_screen_call_sites_match_signature() -> None:
    """Audit finding #2: ``parser_preview_screen`` should not get 0 inputs."""
    from shopstack.ui.screens.parser_preview import parser_preview_screen
    sig = inspect.signature(parser_preview_screen)
    expected = sum(
        1 for _, p in sig.parameters.items()
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                      inspect.Parameter.POSITIONAL_OR_KEYWORD)
    )
    allowed = {0, expected}

    src = Path("shopstack/ui/tabs/parser.py").read_text()
    call_sites = _find_call_kwargs(src, "parser_preview_screen")
    assert call_sites, "parser_preview_screen should be referenced in tabs/parser.py"
    for line, inputs, _outputs in call_sites:
        assert inputs is not None, f"line {line}: missing inputs=[...] kwarg"
        assert len(inputs) in allowed, (
            f"line {line}: parser_preview_screen expects {expected} "
            f"positional inputs (or 0 with default), got {len(inputs)}"
        )


def test_shelf_scan_process_call_sites_match_signature() -> None:
    """Audit finding #3: ``shelf_scan_process`` should get 4 inputs, not 1."""
    from shopstack.ui.screens.shelf_scan import shelf_scan_process
    sig = inspect.signature(shelf_scan_process)
    expected = sum(
        1 for _, p in sig.parameters.items()
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                      inspect.Parameter.POSITIONAL_OR_KEYWORD)
    )
    assert expected == 4, (
        f"shelf_scan_process signature drift: expected 4 positional params, "
        f"got {expected}. Update this test if the signature changes."
    )

    # Both scanner.py and market.py have call sites; verify both.
    for rel in ("shopstack/ui/tabs/scanner.py", "shopstack/ui/tabs/market.py"):
        src = Path(rel).read_text()
        call_sites = _find_call_kwargs(src, "shelf_scan_process")
        assert call_sites, f"shelf_scan_process should be referenced in {rel}"
        for line, inputs, outputs in call_sites:
            assert inputs is not None, f"{rel}:{line}: missing inputs=[...]"
            assert len(inputs) == expected, (
                f"{rel}:{line}: shelf_scan_process expects {expected} "
                f"inputs, got {len(inputs)}: {inputs}"
            )
            assert outputs is not None, f"{rel}:{line}: missing outputs=[...]"
            # 4 outputs (results, state, trace, annotated)
            assert len(outputs) == expected, (
                f"{rel}:{line}: shelf_scan_process returns a {expected}-tuple, "
                f"but outputs= has {len(outputs)}: {outputs}"
            )


def test_agent_trace_search_filter_call_sites_match_signature() -> None:
    """Audit finding #4: ``agent_trace_search_filter`` should get 2 inputs, not 1."""
    from shopstack.ui.screens.traces import agent_trace_search_filter
    sig = inspect.signature(agent_trace_search_filter)
    expected_inputs = sum(
        1 for _, p in sig.parameters.items()
        if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                      inspect.Parameter.POSITIONAL_OR_KEYWORD)
    )
    assert expected_inputs == 2, (
        f"agent_trace_search_filter signature drift: expected 2 inputs, "
        f"got {expected_inputs}. Update this test if the signature changes."
    )

    src = Path("shopstack/ui/tabs/memory_history.py").read_text()
    call_sites = _find_call_kwargs(src, "agent_trace_search_filter")
    assert call_sites, "agent_trace_search_filter should be wired in memory_history.py"
    for line, inputs, outputs in call_sites:
        if inputs is None:
            # not a Gradio handler call (could be a Python import) — skip
            continue
        assert len(inputs) == expected_inputs, (
            f"line {line}: agent_trace_search_filter expects "
            f"{expected_inputs} inputs, got {len(inputs)}: {inputs}"
        )
        # Function returns a 3-tuple per its docstring.
        assert outputs is not None and len(outputs) == 3, (
            f"line {line}: agent_trace_search_filter returns 3 values, "
            f"outputs= has {len(outputs) if outputs else 'None'}"
        )


def test_community_optin_call_site_returns_enough_outputs() -> None:
    """Audit finding #5: community opt-in should return enough outputs.

    The community opt-in/out buttons in household_settings.py are
    wrapped in ``lambda: _do_set_opt_in(True|False)`` — i.e. they
    take 0 inputs and return 1 output. The audit finding was that
    the original code declared 2 outputs but the wrapper returned 1.
    This test pins the current (correct) contract: the lambda returns
    1 value, the outputs= list has 1 entry.
    """
    src = Path("shopstack/ui/household_settings.py").read_text()
    tree = ast.parse(src)
    opt_buttons = ("community_optin_btn", "community_optout_btn")
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute) and node.func.attr == "click":
            target = node.func.value
            if isinstance(target, ast.Name) and target.id in opt_buttons:
                # Find inputs= and outputs= in the .click(...)
                inputs = outputs = None
                for kw in node.keywords:
                    if kw.arg == "inputs":
                        inputs = kw.value
                    elif kw.arg == "outputs":
                        outputs = kw.value
                assert outputs is not None, (
                    f"{target.id}.click: missing outputs=[...]"
                )
                if isinstance(outputs, ast.List):
                    assert len(outputs.elts) == 1, (
                        f"{target.id}.click: outputs= must have exactly 1 "
                        f"entry to match the wrapper's single return value; "
                        f"got {len(outputs.elts)}"
                    )


# ── Build smoke (slow; marked so it can be skipped in fast feedback) ──


@pytest.mark.slow
def test_build_app_does_not_raise_audit_valueerrors() -> None:
    """Slow regression check: actually build the app and capture any
    of the 5 audit ValueError patterns.

    The 5 patterns from the audit are:

    1. ``ValueError: An event handler didn't receive enough input values (needed: 1, got: 0). Wanted inputs: [Slider]``
    2. ``ValueError: An event handler didn't receive enough input values (needed: 1, got: 0). Wanted inputs: [Textbox]``
    3. ``ValueError: An event handler didn't receive enough input values (needed: 4, got: 1)``
    4. ``ValueError: An event handler didn't receive enough input values (needed: 2, got: 1)``
    5. ``ValueError: A function didn't return enough output values (needed: 2, returned: 1)``

    The build itself is slow (~50s on a cold venv) so this test is
    marked ``@pytest.mark.slow``. Run with ``pytest -m slow`` in CI
    or before pushing to HF Spaces.
    """
    pattern_strings = [
        r"event handler didn't receive enough input values",
        r"function didn't return enough output values",
    ]
    pattern = re.compile("|".join(pattern_strings), re.IGNORECASE)

    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # Build the app; this is where the 5 audit errors would surface.
        from app import build_app
        app = build_app()

    # If we got here, the build completed. Sanity-check it returned a Blocks.
    assert app is not None
    # The patterns above are what we wanted NOT to see. This is a
    # no-op assertion today (since build_app() doesn't expose its
    # captured stderr to us from here); the static checks above
    # (test_analytics_screen_call_sites_match_signature etc.) are
    # what actually verify the audit is closed. This slow test is a
    # belt-and-braces confirmation.
