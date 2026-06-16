"""Memory tab — composition only.

This is the "what did we learn?" tab. It composes 9 sub-tabs by
delegating each to its own sub-builder module:

  1. **Recent corrections** → ``memory_data.build_memory_corrections``
     (close the invisible learning loop — see audit 2026-06-15)
  2. **Patterns**     → ``memory_intelligence.build_memory_intelligence``
  3. **Remember**     → ``memory_notes.build_memory_notes``
  4. **What Happened** → ``memory_history.build_memory_history``
  5. **Nutrition**    → ``memory_nutrition.build_memory_nutrition``
  6. **Activity**     → ``memory_activity.build_memory_activity``
  7. **Analytics**    → ``memory_activity.build_memory_analytics``
  8. **Per-member**   → ``memory_activity.build_memory_per_member`` (Phase 11)
  9. **Advanced**     → ``memory_data.build_memory_advanced`` (developer-only)
 10. **Backup**       → ``memory_data.build_memory_backup``

The sub-builder pattern is documented at the module level of each
sub-builder. The composition here is intentionally minimal — just the
``gr.Tabs`` container and calls to the sub-builders.

All sub-tabs are self-contained: no cross-tab references, no Handles
dataclass needed.

Note: The ``if settings.ui_mode == "developer"`` guard for the
Advanced sub-tab is preserved verbatim inside ``memory_data``. The
``settings`` object is imported here only for that gate.
"""
from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.tabs.context import TabContext
from shopstack.ui.tabs.memory_activity import build_memory_activity, build_memory_analytics, build_memory_per_member
from shopstack.ui.tabs.memory_data import (
    build_memory_advanced,
    build_memory_backup,
    build_memory_corrections,
    build_memory_facts,
)
from shopstack.ui.tabs.memory_history import build_memory_history
from shopstack.ui.tabs.memory_intelligence import build_memory_intelligence
from shopstack.ui.tabs.memory_notes import build_memory_notes
from shopstack.ui.tabs.memory_nutrition import build_memory_nutrition


def build_memory_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Memory tab inside the parent's ``gr.Tabs`` context.

    Composes 9 sub-tabs by delegating each to its own sub-builder.
    No business logic lives in this function — all wiring is in the
    sub-builder modules.

    Args:
        blocks: Alias for the parent gr.Blocks. Kept for symmetry with
            other tab builders.
        app: The root :class:`gr.Blocks` instance — passed to each
            sub-builder for ``app.load(...)`` handlers.
        ctx: Shared dependencies (currently unused by any sub-builder,
            but part of the uniform builder signature for symmetry).

    Returns:
        None. The Memory tab is self-contained: no components are
        referenced by other parts of the app, so no TabHandles
        dataclass is needed.
    """
    with gr.Tab(_tab_label("memory"), id="memory"):
        with gr.Tabs():
            # ── Insights answers "what has ShopStack learned?" — the
            # user opens Memory and wants the canonical learning view
            # first. Per the home screen review P2.
            with gr.Tab("Insights"):
                build_memory_facts(app=app, ctx=ctx)

            # ── Recent corrections is the user's window into the
            # learning loop. Putting it first (a) makes the
            # feature discoverable and (b) is the right answer
            # to "what did ShopStack learn?" — the user can
            # audit, accept, or reject before the signal
            # propagates further.
            with gr.Tab("Recent corrections"):
                build_memory_corrections(app=app, ctx=ctx)

            with gr.Tab("Patterns"):
                build_memory_intelligence(app=app, ctx=ctx)

            with gr.Tab("Remember"):
                build_memory_notes(app=app, ctx=ctx)

            with gr.Tab("What Happened"):
                build_memory_history(app=app, ctx=ctx)

            with gr.Tab("Nutrition"):
                build_memory_nutrition(app=app, ctx=ctx)

            with gr.Tab("Activity"):
                build_memory_activity(app=app, ctx=ctx)

            with gr.Tab("Analytics"):
                build_memory_analytics(app=app, ctx=ctx)

            with gr.Tab("Per-member"):
                build_memory_per_member(app=app, ctx=ctx)

            # ── Advanced is developer-only; the sub-builder is a no-op
            # for non-developer modes. The guard lives inside the
            # sub-builder so the sub-tab isn't even added to the tab
            # list for non-developers.
            build_memory_advanced(app=app, ctx=ctx)

            with gr.Tab("Backup"):
                build_memory_backup(app=app, ctx=ctx)
