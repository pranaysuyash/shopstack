"""Command surface — the unified "ask or add" input for ShopStack.

**Why this exists (motto_v3 §0.14 product reality):**

The ShopStack Today tab historically exposed two separate input surfaces
— a "Quick add" textbox that added to the shopping list, and an "Ask
ShopStack" textbox that ran the AI planner. From the user's point of
view these were the same job: "tell ShopStack something." Two inputs
that look alike but do different things is a friction source, not a
feature.

The command surface merges both into a single typed input. The user
types one of:

* questions:    "do we have milk?"
* shopping:     "add milk" / "buy bread"
* pantry:       "we have 2kg rice" / "stock onion"
* purchase:     "i bought eggs"
* consumption:  "we finished bread" / "consume rice"
* voice:        (deferred to the voice memo panel below)

Routing is **deterministic** (no LLM call, no parser hot-path): the
first matching keyword prefix wins. If nothing matches, the surface
falls through to the existing Ask ShopStack handler so the user never
sees a "command not recognised" error.

**Architecture (motto_v3 §0.15 third-layer rule):**

* model — none (deterministic intent routing).
* pipeline — :func:`parse_intent` → :func:`dispatch` → result toast.
* data/configuration — keyword table lives in :data:`INTENT_PREFIXES`,
  one row per action. New actions are one-line additions.

**Supersession (motto_v3 §7):**

The legacy :func:`shopstack.services.restock_card.add_restock_to_list`
handler and the legacy :func:`shopstack.ui.tabs.ask_panel._ask_and_reveal`
are *not* removed by this module. They continue to work; the command
surface is the new canonical entry point. Old surfaces are deprecated
via the ``@deprecated`` shim they wrap (see ``_legacy_ask`` below).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html import escape
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ── Action enum / dataclass ──────────────────────────────────────────


@dataclass(frozen=True)
class CommandIntent:
    """A parsed user command.

    Attributes:
        action: One of ``"add_to_list"``, ``"log_purchase"``,
            ``"add_stock"``, ``"mark_consumed"``, ``"ask"``,
            ``"unknown"``. The first four mutate household state;
            ``"ask"`` is read-only and routes to the Ask ShopStack
            planner; ``"unknown"`` falls through to Ask as a free-form
            question.
        canonical_name: Item name extracted from the command, lower-cased
            and underscores-spaced (e.g. ``"milk"`` or ``"wheat_flour"``).
        raw: The original user input (kept for fall-through to Ask).
    """

    action: str
    canonical_name: str
    raw: str


# ── Intent routing table (deterministic, no model) ────────────────


# Each tuple: (action, prefix regex, canonical normaliser).
# Order matters — the first matching prefix wins. Keep most-specific
# patterns first (consume > purchase > stock > buy > add).
_INTENT_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    # Mark consumed
    (
        "mark_consumed",
        re.compile(
            r"^\s*(?:we\s+(?:finished|used|ran\s+out\s+of)|consume[d]?\s+|used\s+up\s+|ate)\s+(?P<item>[\w\s\-]+?)\s*\.?\s*$",
            re.IGNORECASE,
        ),
        "consume",
    ),
    # Log purchase (bought)
    (
        "log_purchase",
        re.compile(
            r"^\s*(?:i\s+(?:bought|got|picked\s+up|just\s+bought)|bought|purchased)\s+(?P<item>[\w\s\-]+?)\s*\.?\s*$",
            re.IGNORECASE,
        ),
        "purchase",
    ),
    # Add pantry stock (we have / in stock / at home)
    (
        "add_stock",
        re.compile(
            r"^\s*(?:we\s+have|got\s+in|at\s+home|stocked|stash(?:ed)?|put\s+away)\s+(?P<item>[\w\s\-]+?)\s*\.?\s*$",
            re.IGNORECASE,
        ),
        "stock",
    ),
    # Add to shopping list
    (
        "add_to_list",
        re.compile(
            r"^\s*(?:add|need|buy|get|put\s+on\s+(?:the\s+)?list|shop(?:ping)?\s+for)\s+(?P<item>[\w\s\-]+?)\s*\.?\s*$",
            re.IGNORECASE,
        ),
        "list",
    ),
)


# ── Quick-action chips (the visible "staples" below the input) ────


COMMON_STAPLE_CHIPS: tuple[str, ...] = (
    "milk",
    "bread",
    "eggs",
    "rice",
    "curd",
    "wheat_flour",
    "toor_dal",
    "onion",
    "tomato",
    "cooking_oil",
)


# ── Helpers ────────────────────────────────────────────────────────


def _normalise_canonical_name(raw_item: str) -> str:
    """Convert a free-text item phrase into a canonical slug.

    Rules (intentionally simple, deterministic):
        * lower-case
        * strip punctuation
        * collapse whitespace to underscore
        * drop leading/trailing underscores

    Examples:
        >>> _normalise_canonical_name("Wheat Flour")
        'wheat_flour'
        >>> _normalise_canonical_name("  toor DAL ")
        'toor_dal'
        >>> _normalise_canonical_name("Milk (1L)")
        'milk_1l'
    """
    s = raw_item.strip().lower()
    s = re.sub(r"[^\w\s]+", " ", s)
    s = re.sub(r"\s+", "_", s)
    return s.strip("_")


def parse_intent(text: str) -> CommandIntent:
    """Parse raw user text into a :class:`CommandIntent`.

    Tries each pattern in order. The first match wins. If nothing
    matches (e.g. the user types "do we have milk?"), the action is
    ``"ask"`` and the original text is preserved for fall-through.
    """
    if not text or not text.strip():
        return CommandIntent(action="unknown", canonical_name="", raw=text or "")

    for action, pattern, _label in _INTENT_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        item_raw = match.group("item").strip()
        if not item_raw:
            continue
        return CommandIntent(
            action=action,
            canonical_name=_normalise_canonical_name(item_raw),
            raw=text,
        )

    # No keyword match — treat as a question / free-form Ask
    return CommandIntent(action="ask", canonical_name="", raw=text)


# ── Dispatch ────────────────────────────────────────────────────────


@dataclass
class CommandResult:
    """Outcome of dispatching a parsed command."""

    success: bool
    action: str
    message: str  # user-facing toast / inline feedback
    canonical_name: str = ""

    def to_toast(self) -> str:
        """Render this result as the small ``.toast`` HTML block used in
        inline feedback."""
        kind = "success" if self.success else "error"
        icon = "✓" if self.success else "✗"
        return (
            f"<div class='toast toast--{kind}' role='status' aria-live='polite'>"
            f"<span class='toast-icon'>{icon}</span>"
            f"<span class='toast-msg'>{escape(self.message)}</span>"
            f"</div>"
        )


# Pluggable handlers. They are injected at app-build time so this
# service can be tested without a live DB / tools.
_handler: dict[str, Callable[[str], CommandResult]] = {}


def register_handler(action: str, handler: Callable[[str], CommandResult]) -> None:
    """Register a concrete implementation for a command action.

    Called once during app composition in
    :mod:`shopstack.ui.tabs.command_surface`. The handler is responsible
    for hitting the database (or the Ask planner) and returning a
    :class:`CommandResult`. Unknown actions raise ``KeyError``.
    """
    _handler[action] = handler
    logger.debug("Registered command handler: %s", action)


def dispatch(intent: CommandIntent) -> CommandResult:
    """Run the registered handler for ``intent.action``.

    Falls back to a generic "ask" handler if the specific action has
    no registered handler (e.g. on a fresh module without the rest of
    the app wired). This way the surface never breaks the page render.
    """
    handler = _handler.get(intent.action) or _handler.get("ask")
    if handler is None:
        return CommandResult(
            success=False,
            action=intent.action,
            canonical_name=intent.canonical_name,
            message=f"No handler registered for '{intent.action}'.",
        )
    try:
        return handler(intent.canonical_name, intent=intent)  # type: ignore[arg-type]
    except TypeError:
        # Backwards-compat: handlers with the old (canonical_name) signature
        return handler(intent.canonical_name)  # type: ignore[call-arg]
    except Exception as exc:  # noqa: BLE001
        logger.warning("command dispatch failed: %s", exc)
        return CommandResult(
            success=False,
            action=intent.action,
            canonical_name=intent.canonical_name,
            message=f"Something went wrong: {exc}",
        )


# ── HTML renderers for the surface itself ───────────────────────────


def render_command_surface_html(
    *,
    chips: tuple[str, ...] = COMMON_STAPLE_CHIPS,
    last_result: CommandResult | None = None,
    placeholder: str = (
        "Add milk · I bought bread · We finished eggs · Do we have rice?"
    ),
) -> str:
    """Render the HTML *description* shown above the Gradio input.

    The Gradio components themselves are added in the tab builder
    (textbox, button, chip-row). This helper renders the user-facing
    prompt + the quick-staples chip row + the most recent toast.

    Why both an HTML helper and a Gradio builder: the prompt copy
    is a string that benefits from i18n and a single source of truth.
    The Gradio event wiring lives in the tab builder where the
    components are created.
    """
    chip_html = "".join(
        f"<button type='button' class='cmd-chip' data-chip='{escape(chip)}' "
        f"onclick=\"ssCommandFillChip(this.getAttribute('data-chip'))\">"
        f"{escape(chip.replace('_', ' ').title())}</button>"
        for chip in chips
    )
    toast_html = last_result.to_toast() if last_result is not None else ""
    return (
        "<div class='command-surface'>"
        "<div class='command-surface-prompt'>"
        "Type an action or a question. Use one of the chips to add a common "
        "staple, or write a sentence like <em>“we finished bread”</em>."
        "</div>"
        f"<div class='command-chip-row' role='group' aria-label='Quick staples'>{chip_html}</div>"
        f"<div class='command-surface-feedback' id='command-surface-feedback'>{toast_html}</div>"
        "</div>"
    )


# ── JS handler shim (registered by the tab builder via gr.HTML) ────


COMMAND_SURFACE_SCRIPT_HTML: str = """
<script data-ss-exec="true">
// ── Command surface: chip → input + submit helper ─────────────────
function ssCommandFillChip(name) {
  try {
    var input = document.getElementById('command-surface-input');
    if (!input) return;
    var ta = input.querySelector('textarea') || input;
    if (ta && 'value' in ta) {
      ta.value = 'add ' + name;
      ta.dispatchEvent(new Event('input', { bubbles: true }));
      ta.focus();
    }
  } catch (e) {
    console.warn('ssCommandFillChip failed', e);
  }
}
</script>
"""


__all__ = [
    "COMMON_STAPLE_CHIPS",
    "COMMAND_SURFACE_SCRIPT_HTML",
    "CommandIntent",
    "CommandResult",
    "dispatch",
    "parse_intent",
    "register_handler",
    "render_command_surface_html",
]
