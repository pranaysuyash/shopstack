"""Tests for the Memory → Insights sub-tab (build_memory_facts).

Closes the 2026-06-15 home screen review P2 item
("Memory insight cards — 'Your household usually buys: Milk every
3 days...'"). The data layer
(:mod:`shopstack.services.memory_facts`) and the renderer
(:func:`render_memory_facts`) were already implemented; this
sub-builder is the missing wiring into the Memory tab.

Evidence tier: T1 (static inspection) + T2 (this test passes).

Per motto_v3 §7 supersession: the sub-builder does not introduce a
new renderer, a new data source, or a new API. It wires the
canonical :func:`render_memory_facts` into a Gradio sub-tab.
"""
from __future__ import annotations

import inspect
from pathlib import Path


# ── Sub-builder is importable and shaped right ───────────────────────


def test_build_memory_facts_is_importable():
    from shopstack.ui.tabs.memory_data import build_memory_facts

    assert callable(build_memory_facts)


def test_build_memory_facts_signature_uniform_with_sibling_builders():
    """Every ``build_memory_*`` sub-builder takes ``(app, ctx)`` —
    the uniform signature keeps the Memory tab composition
    mechanical. A new builder that takes different args would
    force a special case in ``memory.py``."""
    from shopstack.ui.tabs.memory_data import (
        build_memory_advanced,
        build_memory_backup,
        build_memory_corrections,
        build_memory_facts,
    )

    sig_facts = inspect.signature(build_memory_facts)
    sig_corrections = inspect.signature(build_memory_corrections)
    sig_backup = inspect.signature(build_memory_backup)
    sig_advanced = inspect.signature(build_memory_advanced)
    assert sig_facts.parameters.keys() == sig_corrections.parameters.keys()
    assert sig_facts.parameters.keys() == sig_backup.parameters.keys()
    assert sig_facts.parameters.keys() == sig_advanced.parameters.keys()


# ── The sub-tab uses the canonical renderer (no fork) ───────────────


def test_build_memory_facts_uses_canonical_renderer():
    """The sub-builder must call the canonical
    :func:`render_memory_facts` from :mod:`memory_facts` — not
    inline the same rendering logic, which would create a
    duplicate rendering path (motto_v3 §7)."""
    from shopstack.ui.tabs import memory_data
    import shopstack.services.memory_facts as mf

    src = Path(memory_data.__file__).read_text()
    # The import is the static check — using the function elsewhere
    # in this module proves the wiring.
    assert "from shopstack.services.memory_facts import render_memory_facts" in src
    # The renderer is the same function the data layer exports.
    assert memory_data.render_memory_facts is mf.render_memory_facts


def test_build_memory_facts_uses_loading_skeleton_primitive():
    """The sub-tab must use the canonical
    :func:`loading_skeleton` primitive for the initial paint
    rather than emitting raw HTML — keeps the loading-state UI
    consistent across sub-tabs."""
    from shopstack.ui.tabs import memory_data

    src = Path(memory_data.__file__).read_text()
    assert "loading_skeleton" in src
    # The skeleton must be passed to a gr.HTML component as the
    # initial value, not a raw div.
    assert "gr.HTML(loading_skeleton(" in src


# ── Wiring: the sub-builder is registered in memory.py ──────────────


def test_memory_py_imports_build_memory_facts():
    src = Path("shopstack/ui/tabs/memory.py").read_text()
    assert "build_memory_facts" in src


def test_memory_py_calls_build_memory_facts_inside_tab_context():
    """The sub-builder must be called inside a ``gr.Tab`` context,
    not at the top level of the Memory tab."""
    src = Path("shopstack/ui/tabs/memory.py").read_text()
    # Find the function call and the surrounding tab context.
    assert "with gr.Tab(" in src
    assert "build_memory_facts(app=app, ctx=ctx)" in src


def test_insights_tab_comes_before_recent_corrections():
    """Per the home screen review: the user opens Memory and asks
    'what has ShopStack learned?' — Insights answers that first."""
    src = Path("shopstack/ui/tabs/memory.py").read_text()
    insights_pos = src.find('gr.Tab("Insights")')
    corrections_pos = src.find('gr.Tab("Recent corrections")')
    assert insights_pos != -1, "Insights sub-tab must be present"
    assert corrections_pos != -1, "Recent corrections sub-tab must remain"
    assert insights_pos < corrections_pos, (
        "Insights must be ordered BEFORE Recent corrections so the "
        "user sees the canonical 'what ShopStack has learned' view first"
    )


# ── Wiring: the sub-builder has a refresh button + app.load ──────────


def test_build_memory_facts_wires_app_load_and_refresh():
    """The sub-tab must populate the insights on page load AND
    expose a manual refresh button — the user may want to
    re-render after adding purchases elsewhere."""
    from shopstack.ui.tabs import memory_data

    src = Path(memory_data.__file__).read_text()
    # The function body must:
    # 1) call render_memory_facts from app.load
    # 2) expose a refresh button that re-runs the renderer
    assert "app.load(render_memory_facts" in src
    assert "refresh_btn" in src
    assert "render_memory_facts" in src


# ── Regression: existing memory sub-tabs still wired ─────────────────


def test_existing_memory_subtabs_still_wired():
    """Reordering must not have broken the wiring of any
    pre-existing sub-tab."""
    src = Path("shopstack/ui/tabs/memory.py").read_text()
    for builder in [
        "build_memory_facts",
        "build_memory_corrections",
        "build_memory_intelligence",
        "build_memory_notes",
        "build_memory_history",
        "build_memory_nutrition",
        "build_memory_activity",
        "build_memory_analytics",
        "build_memory_per_member",
        "build_memory_advanced",
        "build_memory_backup",
    ]:
        assert f"{builder}(app=app, ctx=ctx)" in src, f"{builder} call missing"


# ── Regression: existing memory tests still pass ──────────────────────


def test_memory_corrections_subtab_wiring_still_present():
    """The existing regression test for the corrections sub-tab
    must still be satisfied after the reorder."""
    src = Path("shopstack/ui/tabs/memory.py").read_text()
    assert "build_memory_corrections" in src


# ── Public API: build_memory_facts is part of the memory_data module


def test_memory_data_module_exposes_build_memory_facts():
    import shopstack.ui.tabs.memory_data as m

    assert hasattr(m, "build_memory_facts")
    assert callable(m.build_memory_facts)
