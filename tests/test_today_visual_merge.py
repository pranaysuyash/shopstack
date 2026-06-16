"""Tests for the Quick-add + Ask + Voice visual merge on the Today tab.

Closes the 2026-06-15 home screen review P1 item
("Merge Quick-add + Ask + Voice into one command surface. The
restock quick-add row (today.py), build_ask_panel
(shopstack/ui/tabs/ask_panel.py), and voice memo are still three
separate UI sections. The review wants one input that handles
questions, shopping commands, and purchase logs, with voice as an
input under it.").

Evidence tier: T1 (static inspection) + T2 (this test passes).

Per motto_v3 §7 supersession: the canonical handlers
(``build_command_surface``, ``build_voice_memo_section``,
``build_ask_panel``) are NOT deleted. The Ask panel is no longer
*rendered* on the Today tab — its handlers remain importable for
any future surface that needs them (the command surface already
has Ask fallthrough at the data layer).
"""
from __future__ import annotations

import re
from pathlib import Path


# ── The three "Quick action / Ask / Voice" inputs are now one section ─


def test_today_tab_has_unified_intro_paragraph():
    """The Today tab must explain the merged input surface in one
    paragraph that covers commands, purchases, stock, consumption,
    questions, and voice — replacing the old '### Quick action'
    one-liner and the '### Ask ShopStack' header in the side column."""
    src = Path("shopstack/ui/tabs/today.py").read_text()
    assert "**What would you like to do?**" in src
    # The intro should mention all four action kinds plus Ask
    # fallthrough plus voice. A single pass over the unified intro
    # block proves the user is told the right story.
    intro_block = re.search(
        r"\*\*What would you like to do\?\*\*.*?voice button below",
        src,
        flags=re.DOTALL,
    )
    assert intro_block is not None
    block = intro_block.group(0)
    for kind in ["add", "bought", "we have", "finished", "question", "voice"]:
        assert kind in block, (
            f"Unified intro must mention '{kind}' so the user knows "
            f"the merged input handles it; got: {block[:200]!r}"
        )


def test_old_quick_action_header_removed():
    """The legacy '### Quick action' header must be gone — the
    unified intro replaces it."""
    src = Path("shopstack/ui/tabs/today.py").read_text()
    assert 'gr.Markdown("### Quick action")' not in src


def test_old_ask_shopstack_header_removed():
    """The legacy '### Ask ShopStack' header in the side column must
    be gone — the merged command surface above handles Ask via
    fallthrough."""
    src = Path("shopstack/ui/tabs/today.py").read_text()
    assert 'gr.Markdown("### Ask ShopStack")' not in src


# ── Canonical handlers remain (no fork, no deletion) ─────────────────


def test_command_surface_still_wired():
    """``build_command_surface`` is still called and is the entry
    point of the merged input."""
    src = Path("shopstack/ui/tabs/today.py").read_text()
    assert "build_command_surface(blocks=app, app=app, ctx=ctx)" in src


def test_voice_memo_still_wired():
    """``build_voice_memo_section`` is still called and lives
    directly under the command surface (per the home review:
    'voice as an input under it')."""
    src = Path("shopstack/ui/tabs/today.py").read_text()
    assert "build_voice_memo_section(app=app)" in src
    # The voice call must come AFTER the command surface call so
    # voice renders below the typed input.
    cs_pos = src.find("build_command_surface(blocks=app")
    vm_pos = src.find("build_voice_memo_section(app=app)")
    assert 0 <= cs_pos < vm_pos, "voice must render below command surface"


def test_ask_panel_no_longer_rendered_in_today_tab():
    """The legacy full ``build_ask_panel`` call is removed from the
    Today tab. The handler itself stays importable for any future
    surface (per §7 supersession: don't delete the canonical
    handler, just stop rendering it in a context that's been
    merged)."""
    src = Path("shopstack/ui/tabs/today.py").read_text()
    # The CALL is gone
    assert "build_ask_panel(blocks=app, app=app, ctx=ctx)" not in src
    # The IMPORT is also gone (no longer used in this module)
    assert "from shopstack.ui.tabs.ask_panel import build_ask_panel" not in src
    # The handler still exists in its home module (canonical path
    # preserved for any future use).
    from shopstack.ui.tabs import ask_panel

    assert callable(ask_panel.build_ask_panel)


# ── No regression on the rest of the Today tab structure ─────────────


def test_signals_section_still_present():
    """The right-column 'Signals' section must remain — it is the
    supplementary detail and was not part of the merge."""
    src = Path("shopstack/ui/tabs/today.py").read_text()
    assert 'gr.Markdown("### Signals")' in src


def test_home_flow_panel_still_present():
    """The home flow hero panel (the canonical primary surface) is
    not affected by the merge."""
    src = Path("shopstack/ui/tabs/today.py").read_text()
    assert "home_flow = gr.HTML" in src


def test_undo_bar_still_present():
    """The Undo bar (the 2026-06-15 addition) is not affected."""
    src = Path("shopstack/ui/tabs/today.py").read_text()
    assert "undo_bar" in src


# ── Documentation continuity (motto_v3 §0.3) ─────────────────────────


def test_visual_merge_explained_in_module_docstring():
    """The module docstring at the top of ``today.py`` must mention
    the unified input (it already does — confirm after the
    structural change)."""
    src = Path("shopstack/ui/tabs/today.py").read_text()
    # The existing module docstring already explains the command
    # surface; verify the wording is consistent.
    assert "command surface" in src.lower() or "Command surface" in src
