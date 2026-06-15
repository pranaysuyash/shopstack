"""Runtime status API endpoint.

Per AI-9 (see `docs/audits/ACTION_ITEMS.md`): External API consumers
need to know whether they're hitting mock or real providers. This
module wires a hidden Gradio API endpoint that returns the current
runtime mode as a string.

**Why a sub-builder (not inline in app.py):**
- Consistent with the `locale_save.py` and `household_settings.py` pattern
- Isolates the wiring in one testable location
- Future-extensible (could add more diagnostic endpoints: provider
  list, model catalog, etc.)

**Why hidden (visible=False):**
- The endpoint is API-only. No UI consumer needs the button itself.
- The endpoint is wired via `api_name="runtime_status"` so
  `gradio info` shows it.

**Supersession note (motto_v3 §7):**
There are TWO `runtime_label()` functions in the codebase:
- `shopstack.app_context.runtime_label()` (legacy, simpler)
- `shopstack.ui.header.runtime_label()` (canonical, more complete)

This sub-builder uses the CANONICAL version. See
`Docs/DECISION_RECORDS_CODE_REMOVALS_2026-06-13.md` (DR-SS4
proposed) for the supersession of `app_context.runtime_label`.
"""
from __future__ import annotations

from dataclasses import dataclass

import gradio as gr

from shopstack.ui.header import runtime_label


@dataclass
class RuntimeStatusHandles:
    """The hidden input + output for the runtime_status API endpoint.

    Both are invisible (``gr.Textbox(visible=False, ...)``) and
    only accessible via the API (``api_name="runtime_status"``).
    External consumers (CI, deployment scripts, debug tools) POST
    to the input; the submit handler returns the current runtime
    mode to the output.
    """

    status_input: gr.Textbox
    status_output: gr.Textbox


def build_runtime_status() -> RuntimeStatusHandles:
    """Build the hidden runtime_status API endpoint.

    Wires:
      * ``_runtime_input.submit`` → ``_runtime_status_handler`` →
        ``_runtime_output`` (hidden round-trip).
      * The ``api_name="runtime_status"`` makes it callable from
        the client JS via Gradio's client protocol.

    Returns:
        RuntimeStatusHandles: the input and output textboxes. They're
        not referenced anywhere outside this module after construction,
        but exposed for symmetry with the other sub-builders.
    """
    status_input = gr.Textbox(value="", visible=False, elem_id="runtime_status_input")
    status_output = gr.Textbox(value="", visible=False, elem_id="runtime_status_output")

    def _runtime_status_handler(_: str) -> str:
        return runtime_label()

    status_input.submit(
        _runtime_status_handler,
        status_input,
        status_output,
        api_name="runtime_status",
        api_description=(
            "Return the current provider runtime mode. "
            "One of: 'Local mock mode', 'Local runtime', 'Cloud runtime', "
            "'Off-grid mock mode'. Useful for deployment verification."
        ),
    )

    return RuntimeStatusHandles(
        status_input=status_input,
        status_output=status_output,
    )
