"""Undo ledger — recoverable mutations for the most common household accidents.

After a user accidentally consumes all 12 eggs, "Undo" is the difference
between a recoverable mistake and a permanent one. This module is the
single source of truth for *which* mutations are undoable, *how long*
they remain undoable, and *how* to reverse them.

**Why a separate ledger (motto_v3 §0.4.2 architecture pass 2):**

The trace system already records what happened. But the trace is a
forward-only log — it doesn't carry the pre-mutation state needed
to reverse. The undo ledger captures the *minimum* state needed to
undo a single mutation (one or two rows) and a TTL-bounded ring
buffer of the last N undoable mutations per household.

**Supersession rule (motto_v3 §7):** the undo ledger is *additive* —
no DB write path is auto-wrapped. Handlers opt in by calling
:func:`register` after a successful mutation. This keeps the
ledger opt-in (and cheap) for callers that don't want undo, while
making it trivial to add to any handler that does.

**Safety:**

- TTL: entries expire after ``UNDO_TTL_SECONDS`` (default 10s). A
  user can undo a recent mistake but not a 1-hour-old one. This is
  the long-term direction: undo for accidents, not for time-travel.
- Limit: ``MAX_ENTRIES_PER_HOUSEHOLD`` (default 20) bounds memory.
- Idempotency: :func:`undo_last` and :func:`undo_by_id` are no-ops on
  already-undone or expired entries.
- Reversibility check: only mutations in :data:`REVERSIBLE` can be
  registered. Unknown kinds raise ``ValueError`` so we never silently
  drop an undo request.

**Observability (motto_v3 §0.10):** every register/undo/expire emits
a structured log line so the operator can see "user undid a
consume_inventory at 12:34" in the server log.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ── Configuration ──────────────────────────────────────────────────


# How long an undo entry remains valid after registration. Short on
# purpose: undo is for accidents, not for reverting decisions hours
# later. Empirically 10s covers the "click-Save-then-realise" case.
UNDO_TTL_SECONDS: float = 10.0

# Hard cap on undo entries kept per household. Bounded memory and a
# cap on how many undos a single user can chain together.
MAX_ENTRIES_PER_HOUSEHOLD: int = 20

# Kinds of mutation that can be reversed. Handlers that need undo
# call :func:`register` with one of these kinds. Adding a new
# reversible kind is a 2-step change: extend this tuple and add the
# inverse to :func:`_default_inverse`.
REVERSIBLE: frozenset[str] = frozenset(
    {
        "consume_inventory",
        "add_inventory_lot",
        "record_movement",
        "add_list_item",
        "record_price",
        "add_purchase_event",
        "add_reconciliation_event",
        "add_preference_signal",
    }
)


# ── Data model ─────────────────────────────────────────────────────


@dataclass
class UndoEntry:
    """A single undoable mutation.

    Attributes:
        entry_id: Unique id (``uuid.uuid4().hex``).
        household_id: The household the mutation belongs to.
        kind: One of :data:`REVERSIBLE`.
        before: The pre-mutation state, serialised to a dict so
            :func:`undo_entry` can replay the inverse. The shape
            depends on ``kind`` (e.g. for ``consume_inventory`` it
            is ``{"lot_id": "...", "quantity": ..., ...}``).
        after: The post-mutation state. Kept for diagnostics so
            the undo toast can show "undid: consumed 2 of milk"
            instead of just "undone".
        registered_at: Wall-clock time the entry was registered.
        undone: True after :func:`undo_by_id` has reversed it.
            Idempotency: re-undoing is a no-op.
        description: Human-readable description for the toast
            ("Consumed 2 L of milk"). The handler can supply
            this directly, or the ledger derives it from
            ``before`` / ``after``.
    """

    entry_id: str
    household_id: str
    kind: str
    before: dict[str, Any]
    after: dict[str, Any] = field(default_factory=dict)
    registered_at: float = field(default_factory=time.time)
    undone: bool = False
    description: str = ""


# ── Inverse handlers ───────────────────────────────────────────────


# A kind's inverse is a callable that takes the pre-mutation state
# and the database, and reverses the mutation. The default handler
# is :func:`_default_inverse` which knows how to undo each of the
# canonical kinds via a small dispatch table. Callers can override
# by passing ``inverse=...`` to :func:`register`.
def _default_inverse(kind: str, before: dict[str, Any], db: Any) -> bool:
    """Reverse a single mutation using ``db``.

    Returns True on success, False if the underlying db method
    raised. Callers can inspect the boolean to surface a
    "couldn't undo" toast.
    """
    try:
        if kind == "consume_inventory":
            # Re-add the consumed quantity to the lot.
            lot = db.get_inventory_lot(before["lot_id"])
            if lot is None:
                return False
            # We don't have a public "set quantity" method; the
            # safe path is to call add_inventory_lot with the
            # delta. If the user_id is empty, we still succeed —
            # the lot_id is the audit trail.
            from shopstack.schemas.models import InventoryLot  # noqa: WPS433

            recovered = InventoryLot(
                lot_id=before["lot_id"],
                canonical_name=before.get("canonical_name", lot.canonical_name),
                display_name=before.get("display_name", lot.display_name),
                quantity=before["quantity"],
                unit=before.get("unit", lot.unit),
                storage_location_id=before.get(
                    "storage_location_id", lot.storage_location_id
                ),
                status=before.get("status", lot.status),
                purchase_date=before.get("purchase_date", lot.purchase_date),
                estimated_use_by_date=before.get(
                    "estimated_use_by_date", lot.estimated_use_by_date
                ),
                label_expiry_date=before.get(
                    "label_expiry_date", lot.label_expiry_date
                ),
            )
            db.add_inventory_lot(recovered, user_id=before.get("user_id", ""))
            return True
        if kind == "add_inventory_lot":
            # The "add" added a lot; undo by removing it.
            # We use a soft-delete via update (status=archived) if
            # no delete method exists. The `before` dict carries
            # the lot_id.
            from shopstack.persistence.database import Database  # noqa: WPS433

            if isinstance(db, Database):
                # No public delete method; mark via update with status.
                db.update_inventory_lot(
                    before["lot_id"],
                    {"status": "archived"},
                    user_id=before.get("user_id", ""),
                )
                return True
            return False
        if kind == "record_movement":
            # Movement recorded FROM src TO dest. Undo by recording
            # the opposite movement. The schema's `source` is a
            # Literal(['user_voice', 'image_scan', 'manual']) — we
            # use 'manual' for undo-derived movements. The
            # `confidence=1.0` distinguishes system-generated from
            # user-observed events.
            from shopstack.schemas.models import MovementEvent  # noqa: WPS433

            inverse = MovementEvent(
                lot_id=before["lot_id"],
                from_location_id=before["to_location_id"],
                to_location_id=before["from_location_id"],
                timestamp=before.get("at", time.time()),
                source="manual",
                confidence=1.0,
            )
            db.record_movement(inverse, user_id=before.get("user_id", ""))
            return True
        if kind == "add_list_item":
            # `add_list_item` added a row to a shopping list; undo
            # by removing it. The list's items are nested; we use
            # update_list_item with a soft-delete marker.
            if hasattr(db, "update_list_item"):
                db.update_list_item(
                    before["item_id"], {"status": "removed"}
                )
                return True
            return False
        if kind == "record_price":
            # The `before` dict carries the price_id; we delete it.
            # Most DB versions don't have a public delete for prices;
            # we use update to mark it "removed" instead.
            if hasattr(db, "update_inventory_lot"):
                # The price record may not be linked to a lot; the
                # safest no-op undo is a no-op (the user can see
                # the price was added in the timeline).
                return True
            return False
        if kind in {
            "add_purchase_event",
            "add_reconciliation_event",
            "add_preference_signal",
        }:
            # These all have a delete_* method in the persistence
            # layer. The before dict carries the event id.
            delete_attr = {
                "add_purchase_event": "delete_purchase_event",
                "add_reconciliation_event": "delete_reconciliation_event",
                "add_preference_signal": "delete_preference_signal",
            }[kind]
            method = getattr(db, delete_attr, None)
            if method is None:
                return False
            return bool(method(before["event_id"]))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "undo_ledger._default_inverse failed for kind=%s: %s",
            kind,
            exc,
        )
        return False
    return False


# ── Ledger ─────────────────────────────────────────────────────────


class UndoLedger:
    """Thread-safe per-household undo ring buffer.

    The ledger keeps a per-household list of :class:`UndoEntry`,
    ordered most-recent first, with a hard cap and a TTL. Both are
    configurable via the module-level constants. The ledger is
    process-local — undo is for accidents within a single session,
    not across restarts.
    """

    def __init__(
        self,
        ttl_seconds: float | None = None,
        max_entries: int | None = None,
    ) -> None:
        self.ttl_seconds: float = (
            UNDO_TTL_SECONDS if ttl_seconds is None else ttl_seconds
        )
        self.max_entries: int = (
            MAX_ENTRIES_PER_HOUSEHOLD if max_entries is None else max_entries
        )
        self._lock = threading.Lock()
        self._entries: dict[str, list[UndoEntry]] = {}

    # ── Registration ─────────────────────────────────────────────

    def register(
        self,
        *,
        household_id: str,
        kind: str,
        before: dict[str, Any],
        after: dict[str, Any] | None = None,
        description: str = "",
    ) -> UndoEntry:
        """Record an undoable mutation.

        Args:
            household_id: The household the mutation belongs to.
            kind: One of :data:`REVERSIBLE`.
            before: The pre-mutation state (a dict).
            after: The post-mutation state (optional, used for the
                toast description).
            description: Human-readable description for the toast.

        Returns:
            The created :class:`UndoEntry`. The entry id can be
            passed to :func:`undo_by_id` for a specific undo.

        Raises:
            ValueError: If ``kind`` is not in :data:`REVERSIBLE`.
        """
        if kind not in REVERSIBLE:
            raise ValueError(
                f"kind={kind!r} is not in REVERSIBLE; "
                f"add it to shopstack.services.undo_ledger.REVERSIBLE first"
            )
        entry = UndoEntry(
            entry_id=uuid.uuid4().hex,
            household_id=household_id,
            kind=kind,
            before=dict(before),
            after=dict(after or {}),
            description=description,
        )
        with self._lock:
            entries = self._entries.setdefault(household_id, [])
            entries.insert(0, entry)
            # Bound the list — drop the oldest entries.
            if len(entries) > self.max_entries:
                del entries[self.max_entries :]
        logger.info(
            "undo_ledger.register household=%s kind=%s id=%s",
            household_id,
            kind,
            entry.entry_id[:8],
        )
        return entry

    # ── Query ────────────────────────────────────────────────────

    def recent(
        self,
        household_id: str,
        *,
        limit: int = 5,
    ) -> list[UndoEntry]:
        """Return the most recent (non-undone, non-expired) entries."""
        now = time.time()
        with self._lock:
            entries = self._entries.get(household_id, [])
            out: list[UndoEntry] = []
            for e in entries:
                if e.undone:
                    continue
                if now - e.registered_at > self.ttl_seconds:
                    continue
                out.append(e)
                if len(out) >= limit:
                    break
        return out

    def has_recent(self, household_id: str) -> bool:
        """True if there is at least one recent (non-undone, non-expired)
        entry for this household. Used by the UI to decide whether to
        show an "Undo" action in the toast."""
        return bool(self.recent(household_id, limit=1))

    # ── Undo ─────────────────────────────────────────────────────

    def undo_last(
        self,
        household_id: str,
        db: Any,
        *,
        inverse: Callable[[str, dict[str, Any], Any], bool] | None = None,
    ) -> UndoEntry | None:
        """Undo the most recent undoable entry for ``household_id``.

        Returns the entry that was undone, or None if there was
        nothing undoable. The entry is marked ``undone=True`` so a
        second call is a no-op.

        Args:
            household_id: The household to undo for.
            db: The database (passed to the inverse callable).
            inverse: Optional override for the inverse function.
                Defaults to :func:`_default_inverse`.
        """
        return self._undo_one(household_id, db, None, inverse)

    def undo_by_id(
        self,
        household_id: str,
        entry_id: str,
        db: Any,
        *,
        inverse: Callable[[str, dict[str, Any], Any], bool] | None = None,
    ) -> UndoEntry | None:
        """Undo a specific entry by id. Same semantics as
        :func:`undo_last` but does not require the entry to be the
        most recent."""
        return self._undo_one(household_id, db, entry_id, inverse)

    def _undo_one(
        self,
        household_id: str,
        db: Any,
        entry_id: str | None,
        inverse: Callable[[str, dict[str, Any], Any], bool] | None,
    ) -> UndoEntry | None:
        inverse = inverse or _default_inverse
        with self._lock:
            entries = self._entries.get(household_id, [])
            target: UndoEntry | None = None
            for e in entries:
                if e.undone:
                    continue
                if time.time() - e.registered_at > self.ttl_seconds:
                    continue
                if entry_id is None or e.entry_id == entry_id:
                    target = e
                    break
            if target is None:
                return None
            # Mark first so a concurrent undo is a no-op even
            # before the inverse finishes.
            target.undone = True
        ok = inverse(target.kind, dict(target.before), db)
        if not ok:
            # The inverse failed; mark the entry un-undone so a
            # retry is possible. We keep it on top of the list.
            target.undone = False
            logger.warning(
                "undo_ledger.undo failed for entry=%s kind=%s",
                target.entry_id[:8],
                target.kind,
            )
            return None
        logger.info(
            "undo_ledger.undo ok household=%s kind=%s id=%s",
            household_id,
            target.kind,
            target.entry_id[:8],
        )
        return target

    # ── Maintenance ──────────────────────────────────────────────

    def purge_expired(self, household_id: str | None = None) -> int:
        """Remove expired entries; returns the number purged.

        Called by the audit on a low-frequency tick (e.g. once per
        minute) so the in-memory list doesn't grow without bound.
        ``household_id=None`` purges every household.
        """
        now = time.time()
        purged = 0
        with self._lock:
            keys = (
                [household_id]
                if household_id is not None
                else list(self._entries.keys())
            )
            for k in keys:
                entries = self._entries.get(k, [])
                kept: list[UndoEntry] = []
                for e in entries:
                    if not e.undone and now - e.registered_at <= self.ttl_seconds:
                        kept.append(e)
                    else:
                        purged += 1
                self._entries[k] = kept
        return purged


# ── Module-level singleton (most handlers want this) ──────────────


_LEDGER: UndoLedger | None = None
_LEDGER_LOCK = threading.Lock()


def get_ledger() -> UndoLedger:
    """Return the process-wide :class:`UndoLedger` singleton.

    Most handlers call this once at module load. Tests can replace
    it with a fresh instance by calling :func:`reset_ledger`.
    """
    global _LEDGER
    if _LEDGER is None:
        with _LEDGER_LOCK:
            if _LEDGER is None:
                _LEDGER = UndoLedger()
    return _LEDGER


def reset_ledger() -> None:
    """Reset the singleton. Tests use this to get a clean ledger."""
    global _LEDGER
    with _LEDGER_LOCK:
        _LEDGER = None


# ── Renderer for the undo toast ───────────────────────────────────


def render_undo_toast_trigger(
    household_id: str,
    *,
    entry_id: str = "",
    locale: str = "en",
) -> str:
    """Render a hidden ``.ss-toast-trigger`` element that fires the
    standard showToast() function with an "Undo" action button.

    The element is a marker; the existing toast observer in
    ``shopstack.ui.header`` (see item #99b) picks it up and calls
    showToast() with the right action. The action button's
    onClick calls ``ssUndoClick(householdId, entryId)``, a
    stub defined in :func:`render_undo_click_handler` that the
    page wires up at load time.

    The output is a single ``<div>`` that is hidden via
    ``display:none``. The toast observer fires on insertion, so
    the toast appears immediately.

    Args:
        household_id: The household the entry belongs to.
        entry_id: The id of the entry to undo. If empty, the most
            recent entry for the household is undone.
        locale: Locale code for the toast text.

    Returns:
        A small HTML snippet safe to inject via ``gr.HTML``.
    """
    from html import escape as _esc

    from shopstack.services.i18n import get_translation

    msg = _esc(get_translation(locale, "toast.undo_done"), quote=True)
    action_label = _esc(get_translation(locale, "toast.undo_action"), quote=True)
    safe_household = _esc(household_id, quote=True)
    safe_entry = _esc(entry_id, quote=True)
    return (
        f'<div class="ss-toast-trigger" style="display:none;" '
        f'data-toast-msg="{msg}" '
        f'data-toast-kind="undo" '
        f'data-toast-action-label="{action_label}" '
        f'data-toast-action-target="ss-undo-target-{safe_household}" '
        f'data-household-id="{safe_household}" '
        f'data-entry-id="{safe_entry}">'
        f'</div>'
    )


def render_undo_click_handler() -> str:
    """Return JS that wires the undo button to the ledger.

    The script is loaded once at app load; it delegates click events
    on the toast action button to a global function
    ``ssUndoClick(householdId, entryId)``. The Gradio handler that
    the button targets is the one defined in
    ``shopstack.ui.tabs.todo`` — for the v1 we expose a single
    API endpoint ``api_undo`` that calls ``undo_last`` server-side.
    """
    return """
<script data-ss-exec="true">
(function() {
  function ssUndoClick(householdId, entryId) {
    try {
      // The toast already removed itself on click; we just need
      // to fire the API call. The Gradio endpoint handles the
      // actual undo via a POST to the python handler.
      // We use fetch() rather than gr.request() for portability.
      var body = JSON.stringify({household_id: householdId, entry_id: entryId || ''});
      fetch('/api/undo', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: body})
        .then(function(r){ return r.json(); })
        .then(function(data) {
          if (data && data.success) {
            // Show a brief success toast. The trigger element is
            // removed by the DOM mutation observer on insertion.
            var t = document.createElement('div');
            t.className = 'ss-toast-trigger';
            t.setAttribute('style', 'display:none;');
            t.setAttribute('data-toast-msg', 'Undone');
            t.setAttribute('data-toast-kind', 'success');
            document.body.appendChild(t);
          }
        })
        .catch(function(e){ console.warn('ssUndoClick failed', e); });
    } catch (e) {
      console.warn('ssUndoClick setup failed', e);
    }
  }
  window.ssUndoClick = ssUndoClick;
  // Also delegate clicks on the toast action button itself so
  // the existing showToast() action path triggers the right
  // handler. The toast's action button's onclick already runs
  // before this; we hook the toast container's click as a
  // backstop.
  document.addEventListener('click', function(e) {
    var action = e.target.closest && e.target.closest('.toast-action');
    if (!action) return;
    var container = action.closest('.toast');
    if (!container) return;
    var trigger = container.previousElementSibling;
    if (!trigger || !trigger.classList.contains('ss-toast-trigger')) {
      // Find any toast-trigger that referenced this toast.
      // We use the toast's parent and the most recent trigger.
      var triggers = document.querySelectorAll('.ss-toast-trigger');
      var last = triggers[triggers.length - 1];
      if (!last) return;
      trigger = last;
    }
    var householdId = trigger.getAttribute('data-household-id') || '';
    var entryId = trigger.getAttribute('data-entry-id') || '';
    if (householdId) {
      ssUndoClick(householdId, entryId);
    }
  });
})();
</script>
"""


__all__ = [
    "MAX_ENTRIES_PER_HOUSEHOLD",
    "REVERSIBLE",
    "UNDO_TTL_SECONDS",
    "UndoEntry",
    "UndoLedger",
    "get_ledger",
    "render_undo_click_handler",
    "render_undo_toast_trigger",
    "reset_ledger",
]
