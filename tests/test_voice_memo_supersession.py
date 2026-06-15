"""Regression tests for the voice_memo shadow-drop fix (2026-06-15).

Per `motto_v3` §7 (Supersession / Canonical Replacement Rule): when a
newer canonical module supersedes an inline implementation, the inline
must be removed (not left in place) and a backward-compat alias
preserved at the old path. The voice_memo shadow-drop was caused by
the inline copy in `shopstack/ui/tabs/ask_panel.py::build_ask_panel`
registering the same `api_name` ("voice_memo_process", "voice_memo_reset")
as the canonical implementation in
`shopstack/ui/tabs/voice_memo.py::build_voice_memo_section`. Gradio
silently overrides the second registration, dropping the canonical
handler.

These tests guard against the regression by:

1. **Static source check** — `test_ask_panel_does_not_define_voice_memo`:
   Asserts that `shopstack/ui/tabs/ask_panel.py` no longer contains
   `api_name="voice_memo_process"` or `api_name="voice_memo_reset"`
   in its source. This catches any future re-introduction of the
   inline copy before it can shadow the canonical registration.

2. **Alias preserved** — `test_ask_panel_alias_delegates_to_canonical`:
   Asserts that the `build_voice_memo_section` symbol still exists
   in `shopstack.ui.tabs.ask_panel` and delegates to the canonical
   module. Per motto_v3 §7, the alias must remain until all callers
   migrate; this test prevents accidental removal.

3. **Exactly one registration per name** — covered by the existing
   `tests/test_api_discoverability.py::test_all_api_names_unique`,
   which is the primary test that flagged the original bug. This
   module complements it with a targeted regression that pinpoints
   the specific file responsible for the historical shadow.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ASK_PANEL = ROOT / "shopstack" / "ui" / "tabs" / "ask_panel.py"
VOICE_MEMO = ROOT / "shopstack" / "ui" / "tabs" / "voice_memo.py"


def _api_names_in_file(path: Path) -> set[str]:
    """Return the set of string-literal ``api_name`` values in *path*."""
    if not path.exists():
        return set()
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "api_name":
                continue
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                names.add(kw.value.value)
    return names


def test_ask_panel_does_not_define_voice_memo():
    """ask_panel.py must not register voice_memo_process / voice_memo_reset.

    The canonical registration lives in voice_memo.py. A second
    registration in ask_panel.py caused a shadow-drop bug (Gradio
    silently overrode one handler). This test fails fast if a
    future change re-introduces the inline copy.
    """
    api_names = _api_names_in_file(ASK_PANEL)
    assert "voice_memo_process" not in api_names, (
        f"ask_panel.py must not register api_name='voice_memo_process' "
        f"(canonical: voice_memo.py). Inline copy was removed 2026-06-15 "
        f"per motto_v3 §7 supersession."
    )
    assert "voice_memo_reset" not in api_names, (
        f"ask_panel.py must not register api_name='voice_memo_reset' "
        f"(canonical: voice_memo.py). Inline copy was removed 2026-06-15 "
        f"per motto_v3 §7 supersession."
    )


def test_voice_memo_canonical_defines_voice_memo():
    """voice_memo.py must register voice_memo_process and voice_memo_reset.

    Sanity check: the canonical implementation is the only
    registration site. If this fails, the canonical module was
    renamed or moved and the supersession target needs to be
    updated.
    """
    api_names = _api_names_in_file(VOICE_MEMO)
    assert "voice_memo_process" in api_names, (
        f"voice_memo.py (canonical) must register api_name='voice_memo_process'. "
        f"Found: {sorted(api_names)}"
    )
    assert "voice_memo_reset" in api_names, (
        f"voice_memo.py (canonical) must register api_name='voice_memo_reset'. "
        f"Found: {sorted(api_names)}"
    )


def test_ask_panel_alias_delegates_to_canonical():
    """ask_panel.build_voice_memo_section is a backward-compat alias.

    Per motto_v3 §7, when superseding old code, preserve a
    compatibility alias at the old path until all in-tree callers
    migrate. The alias must:
    - exist on the old module
    - delegate to the canonical implementation (not register its
      own duplicate api_name)

    The alias is a thin wrapper function, so we cannot compare
    function identity (``is``). Instead we verify the alias's
    source code references the canonical module (delegation) and
    that no Gradio API registrations live in the alias itself.
    """
    import inspect

    import shopstack.ui.tabs.ask_panel as ap
    assert hasattr(ap, "build_voice_memo_section"), (
        "ask_panel.build_voice_memo_section alias was removed. "
        "Per motto_v3 §7, preserve the alias until all in-tree "
        "callers migrate to the canonical import path."
    )

    # The alias must delegate to the canonical module — verified by
    # the function source mentioning the canonical import path.
    src = inspect.getsource(ap.build_voice_memo_section)
    assert "shopstack.ui.tabs.voice_memo" in src, (
        "ask_panel.build_voice_memo_section must delegate to the "
        "canonical shopstack.ui.tabs.voice_memo module. Found source:\n"
        f"{src}"
    )

    # The alias must not register its own api_name endpoints — that
    # is the regression we are guarding against. The alias source
    # must not contain any ``api_name=`` keyword argument.
    assert "api_name" not in src, (
        "ask_panel.build_voice_memo_section alias must not register "
        "Gradio api_name endpoints. The alias is a thin wrapper; the "
        "canonical voice_memo.py is the only registration site. "
        f"Found source:\n{src}"
    )


@pytest.mark.parametrize("api_name", ["voice_memo_process", "voice_memo_reset"])
def test_voice_memo_api_name_registered_exactly_once(api_name: str):
    """Across the whole shopstack/ui tree, voice_memo_* is registered once.

    Belt-and-suspenders complement to
    `tests/test_api_discoverability.py::test_all_api_names_unique`,
    which catches ANY duplicate api_name. This test gives a
    targeted failure with a clear message if the voice_memo
    shadow-drop ever returns.
    """
    ui_dir = ROOT / "shopstack" / "ui"
    offenders: list[tuple[str, int]] = []
    for src in ui_dir.rglob("*.py"):
        if not src.exists():
            continue
        try:
            tree = ast.parse(src.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if (
                    kw.arg == "api_name"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value == api_name
                ):
                    rel = src.relative_to(ROOT)
                    offenders.append((str(rel), node.lineno))

    assert len(offenders) == 1, (
        f"api_name={api_name!r} must be registered exactly once "
        f"in shopstack/ui/, but found {len(offenders)} registrations: "
        f"{offenders}. The 2026-06-15 shadow-drop regression was "
        f"caused by 2 registrations of this name; this guard "
        f"prevents re-introduction."
    )
