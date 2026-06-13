"""Locale save handler — hidden i18n persistence API endpoint.

This is the Gradio API endpoint that the i18n language-selector
buttons in the header (``EN``, ``हिं``) post to when the user
clicks them. The endpoint persists the new locale via
:func:`save_locale_preference`; on the NEXT page load,
:func:`load_locale_preference` returns the freshly-saved locale
and the header re-renders in the new language.

**Why a separate module:**

The handler is small (37 lines in the original ``app.py``) but
its concerns are distinct from the rest of ``build_app()``:

* It defines a hidden input + output + submit handler that the
  JS in the header's ``setLocale()`` function POSTs to.
* It's the only way the user can change locale at runtime
  (no other UI surfaces for it).
* It exists so the header can talk back to the server without
  a visible UI control.

**Why not a Gradio ``gr.State`` with auto-binding:**

The header's JS is plain JS (no Gradio state binding), and the
i18n module already has a clean ``save_locale_preference`` /
``load_locale_preference`` pair. Wrapping those in a hidden
submit handler is the smallest viable API surface.

Extracted from ``app.py`` in Pass 7 to keep ``build_app()`` as
a true composition root (each top-level concern in its own
module).
"""
from __future__ import annotations

from dataclasses import dataclass

import gradio as gr

from shopstack.services.i18n import DEFAULT_LOCALE, save_locale_preference


@dataclass
class LocaleSaveHandles:
    """The hidden input + output for the locale-save API endpoint.

    Both are invisible (``gr.Textbox(visible=False, ...)``) and
    only accessible via the API (``api_name="save_locale"``).
    The header's JS ``setLocale()`` posts the chosen locale to
    the input; the submit handler persists it and echoes the
    value to the output.
    """

    locale_input: gr.Textbox
    locale_output: gr.Textbox


def build_locale_save() -> LocaleSaveHandles:
    """Build the hidden locale-save API endpoint.

    Wires:
      * ``_locale_input.submit`` → ``_save_locale_handler`` →
        ``_locale_output`` (hidden round-trip).
      * The ``api_name="save_locale"`` makes it callable from
        the client JS via Gradio's client protocol.

    Returns:
        LocaleSaveHandles: the input and output textboxes. They're
        not referenced anywhere outside this module after
        construction, but exposed for symmetry with the other
        sub-builders.
    """
    from shopstack.app_context import current_user_id

    locale_input = gr.Textbox(
        value=DEFAULT_LOCALE, visible=False, elem_id="save_locale_input"
    )
    locale_output = gr.Textbox(
        value=DEFAULT_LOCALE, visible=False, elem_id="save_locale_output"
    )

    def _save_locale_handler(locale: str) -> str:
        save_locale_preference(current_user_id() or "default_household", locale)
        return locale

    locale_input.submit(
        _save_locale_handler,
        locale_input,
        locale_output,
        api_name="save_locale",
        api_description=(
            "Persist the chosen locale for the active household. "
            "Called by the i18n language-selector buttons via fetch()."
        ),
    )

    return LocaleSaveHandles(
        locale_input=locale_input,
        locale_output=locale_output,
    )
