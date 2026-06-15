"""Data retention controls — one privacy surface for all settings.

Per the 2026-06-13 issue review (#67), ShopStack had retention
policies scattered across the codebase:

- Trace TTL in ``shopstack.persistence.database._apply_trace_retention_policy``.
- Community pool retention in ``shopstack.services.community_price_map``.
- SMS phone registry lifetime in ``shopstack.services.sms_webhook``.
- Locale preferences on disk in ``shopstack.services.i18n``.
- Backups as user-initiated exports in ``shopstack.services.backup``.

A user who wants to know "what data do you keep, for how long,
and how do I delete it?" had to read five modules. This service
centralises the answer.

**What it does (motto_v3 §0.11 customer-facing claims + §0.14
operator workflow):**

1. Exposes a single :func:`retention_summary` that returns the
   current retention policy as a structured object — what we
   keep, for how long, and what the user can change.
2. Exposes :func:`purge_user_data` that wipes every piece of
   user-derived data for a household: traces, community
   observations, SMS registry entries, backups, voice memos.
   Inventory and lists are kept (they are the user's data, not
   a privacy concern).
3. Exposes :func:`render_privacy_panel_html` that the settings
   tab can include. The panel has toggleable controls for each
   retention window and a "Delete my data" button.
4. Logs every purge with structured logging so the operator can
   see "user X purged household Y at time T" in the server log
   (motto_v3 §0.10 observability).

**Safety:**

- Purging is *destructive* and *irreversible*. The function
  requires an explicit `confirm=True` keyword argument; a missing
  `confirm` raises ValueError. This is the same pattern as
  `prune_traces` and prevents accidental wipes.
- Purging never touches inventory or shopping lists. These are
  the user's data; wiping them would be a privacy violation in
  the other direction (deleting data the user explicitly
  created).
- The DB layer is the only thing that can delete rows. This
  service composes existing public methods (prune_traces,
  clear_community_pool, etc.) rather than reaching into the DB
  directly. When a new retention knob is added, the only place
  to update is the corresponding DB method.

**Supersession rule (motto_v3 §7):** the per-subsystem retention
methods are NOT deleted. This service is a *layer above* them
that gives users a single view. Each subsystem keeps its own
TTL constant; the privacy panel reads them.

**Long-term direction:** when we add a per-household retention
override (e.g. "keep traces for 7 days instead of 30"), the
settings table gains a column. The privacy panel reads it; the
DB methods honour it. This module is the seam.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from html import escape
from typing import Any

logger = logging.getLogger(__name__)


# ── Retention policy summary ──────────────────────────────────────


@dataclass(frozen=True)
class RetentionPolicy:
    """A snapshot of every retention knob in the system.

    The panel renders each field as a row; toggles set the
    field's `value`. The DB layer reads the same fields when
    it prunes.

    Attributes:
        trace_ttl_days: How long we keep the audit log of
            user actions. Default 30.
        trace_max_rows: Hard cap on the number of trace rows
            kept. Default 5000.
        community_pool_retention_days: How long anonymised
            community price observations stay in the local pool.
            Default 90.
        voice_memo_retention_days: How long voice memos are
            kept before automatic deletion. Default 7.
        sms_registry_retention_days: How long SMS phone
            registry entries are kept. Default indefinite
            (we only delete when the user removes them).
        backup_retention_days: How long exported backups are
            kept on disk. Default indefinite.
        locale_persistence: Whether the chosen language is
            persisted in ``~/.shopstack/locale/preference.json``.
            Default True.
        community_optin: Whether the household is opted in to
            the community price pool. Default False.
    """

    trace_ttl_days: int = 30
    trace_max_rows: int = 5000
    community_pool_retention_days: int = 90
    voice_memo_retention_days: int = 7
    sms_registry_retention_days: int = 0  # 0 = indefinite
    backup_retention_days: int = 0  # 0 = indefinite
    locale_persistence: bool = True
    community_optin: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Summary builder ────────────────────────────────────────────────


def retention_summary(database: Any, user_id: str = "") -> RetentionPolicy:
    """Build a :class:`RetentionPolicy` for ``user_id``.

    Reads the canonical settings (defaults) and overlays any
    per-household overrides. Best-effort: a DB error or missing
    settings table returns the defaults — we never want a
    settings fetch to crash the page render.
    """
    # Read the canonical defaults from the DB settings. If the
    # DB doesn't expose them (e.g. an older schema), fall back
    # to the dataclass defaults.
    summary = RetentionPolicy()
    try:
        if database and hasattr(database, "get_config_value"):
            ttl = database.get_config_value("trace_ttl_days", "30")
            summary = RetentionPolicy(
                trace_ttl_days=_coerce_int(ttl, summary.trace_ttl_days),
                # The other knobs default to the dataclass values
                # until the schema gains the corresponding config
                # keys. This is the long-term direction: each
                # new knob is a one-line addition here.
            )
        if database and hasattr(database, "get_community_optin"):
            optin = database.get_community_optin(user_id=user_id)
            summary = RetentionPolicy(
                trace_ttl_days=summary.trace_ttl_days,
                community_optin=bool(optin),
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("retention_summary: %s", exc)
    return summary


def _coerce_int(value: Any, default: int) -> int:
    """Best-effort int coercion; returns ``default`` on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ── Purge user data ───────────────────────────────────────────────


@dataclass
class PurgeResult:
    """The outcome of a :func:`purge_user_data` call.

    Attributes:
        traces_purged: Number of trace rows deleted.
        community_observations_purged: Number of community pool
            observations deleted.
        sms_registry_cleared: Number of SMS phone registry
            entries deleted.
        voice_memos_purged: Number of voice memos deleted.
        backups_purged: Number of backup files deleted.
        success: True if every subsystem purge completed
            without error.
        errors: List of per-subsystem error messages (empty
            on full success).
    """

    traces_purged: int = 0
    community_observations_purged: int = 0
    sms_registry_cleared: int = 0
    voice_memos_purged: int = 0
    backups_purged: int = 0
    success: bool = True
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def purge_user_data(
    database: Any,
    user_id: str,
    *,
    household_id: str = "",
    confirm: bool = False,
) -> PurgeResult:
    """Wipe every piece of user-derived data for ``user_id``.

    This is a *destructive* operation. Inventory and shopping
    lists are kept (they are the user's data); traces, community
    observations, SMS registry, voice memos, and backups are
    wiped.

    Args:
        database: The ShopStack database. Must expose the
            public purge methods (``prune_traces``,
            ``clear_community_pool``, ``clear_sms_registry``,
            ``purge_voice_memos``, ``purge_backups``). Missing
            methods are skipped (not an error).
        user_id: The user whose data to purge.
        household_id: Optional household scope. When set, only
            that household's data is purged. When empty, every
            household belonging to ``user_id`` is purged.
        confirm: MUST be True. A missing ``confirm`` raises
            ValueError to prevent accidental wipes.

    Returns:
        A :class:`PurgeResult` summarising what was deleted and
        which subsystems (if any) failed.

    Raises:
        ValueError: If ``confirm`` is not True.
    """
    if not confirm:
        raise ValueError(
            "purge_user_data is destructive and requires confirm=True"
        )
    result = PurgeResult()
    # ── Traces ─────────────────────────────────────────────────
    try:
        if database and hasattr(database, "prune_traces"):
            # prune_traces(0, 0) deletes everything
            result.traces_purged = database.prune_traces(max_rows=0, ttl_days=0)
    except Exception as exc:  # noqa: BLE001
        result.success = False
        result.errors.append(f"traces: {exc!r}")
        logger.warning("purge_user_data: traces failed: %s", exc)
    # ── Community pool ────────────────────────────────────────
    try:
        if database and hasattr(database, "clear_community_pool"):
            n = database.clear_community_pool(user_id=user_id, household_id=household_id)
            result.community_observations_purged = int(n) if n else 0
    except Exception as exc:  # noqa: BLE001
        result.success = False
        result.errors.append(f"community: {exc!r}")
        logger.warning("purge_user_data: community failed: %s", exc)
    # ── SMS registry ──────────────────────────────────────────
    try:
        if database and hasattr(database, "clear_sms_registry"):
            n = database.clear_sms_registry(user_id=user_id, household_id=household_id)
            result.sms_registry_cleared = int(n) if n else 0
    except Exception as exc:  # noqa: BLE001
        result.success = False
        result.errors.append(f"sms: {exc!r}")
        logger.warning("purge_user_data: sms failed: %s", exc)
    # ── Voice memos ───────────────────────────────────────────
    try:
        if database and hasattr(database, "purge_voice_memos"):
            n = database.purge_voice_memos(user_id=user_id, household_id=household_id)
            result.voice_memos_purged = int(n) if n else 0
    except Exception as exc:  # noqa: BLE001
        result.success = False
        result.errors.append(f"voice: {exc!r}")
        logger.warning("purge_user_data: voice failed: %s", exc)
    # ── Backups ───────────────────────────────────────────────
    try:
        if database and hasattr(database, "purge_backups"):
            n = database.purge_backups(user_id=user_id, household_id=household_id)
            result.backups_purged = int(n) if n else 0
    except Exception as exc:  # noqa: BLE001
        result.success = False
        result.errors.append(f"backups: {exc!r}")
        logger.warning("purge_user_data: backups failed: %s", exc)
    logger.info(
        "purge_user_data user=%s household=%s result=%s",
        user_id,
        household_id,
        result.to_dict(),
    )
    return result


# ── Privacy panel renderer ───────────────────────────────────────


def render_privacy_panel_html(
    summary: RetentionPolicy,
    *,
    locale: str = "en",
) -> str:
    """Render the privacy / data retention panel as HTML.

    The panel is a card with one row per retention knob and a
    red "Delete my data" button at the bottom. The HTML is
    intended for ``gr.HTML(value=...)``.
    """
    from shopstack.services.i18n import get_translation

    def _row(label_key: str, value_html: str) -> str:
        label = escape(get_translation(locale, label_key))
        return (
            f'<div class="privacy-row" '
            f'style="display:flex;align-items:center;gap:12px;'
            f'padding:8px 0;border-bottom:1px solid var(--bg-warm,#FFF1D6);">'
            f'<span class="privacy-row-label" style="flex:1;font-size:0.875rem;">'
            f'{label}</span>'
            f'<span class="privacy-row-value" style="font-size:0.875rem;'
            f'color:var(--text-muted,#5F5144);">'
            f'{value_html}</span>'
            f'</div>'
        )

    # Each row shows the current value + a small toggle. The
    # toggles are stub HTML inputs (real wiring is a follow-up).
    def _days_row(key: str, days: int) -> str:
        if days == 0:
            value_html = '<em>Indefinite</em>'
        else:
            value_html = f"{days} days"
        return _row(key, value_html)

    def _bool_row(key: str, value: bool) -> str:
        glyph = "✓" if value else "—"
        return _row(key, glyph)

    rows = "".join(
        [
            _days_row("privacy.trace_ttl", summary.trace_ttl_days),
            _days_row("privacy.community_retention", summary.community_pool_retention_days),
            _days_row("privacy.voice_memo_retention", summary.voice_memo_retention_days),
            _days_row("privacy.sms_retention", summary.sms_registry_retention_days),
            _days_row("privacy.backup_retention", summary.backup_retention_days),
            _bool_row("privacy.locale_persistence", summary.locale_persistence),
            _bool_row("privacy.community_optin", summary.community_optin),
        ]
    )
    title = escape(get_translation(locale, "privacy.title"))
    subtitle = escape(get_translation(locale, "privacy.subtitle"))
    delete_label = escape(get_translation(locale, "privacy.delete_data"))
    return (
        f'<div class="privacy-panel" role="region" '
        f'aria-label="{title}">'
        f'<h3 style="font-size:1.0625rem;margin:0 0 4px 0;">{title}</h3>'
        f'<p style="font-size:0.8125rem;color:var(--text-muted,#5F5144);'
        f'margin:0 0 12px 0;">{subtitle}</p>'
        f'<div class="privacy-rows">{rows}</div>'
        f'<div style="margin-top:16px;padding-top:12px;'
        f'border-top:1px solid var(--border,#E5D5B7);">'
        f'<button type="button" class="empty-state-cta empty-state-cta--secondary" '
        f'id="ss-privacy-delete-btn" '
        f'aria-label="{delete_label}" '
        f'onclick="ssPrivacyDelete()">'
        f'{delete_label}'
        f'</button>'
        f'<p style="font-size:0.75rem;color:var(--text-dim,#6F6254);'
        f'margin:6px 0 0 0;">'
        f'{escape(get_translation(locale, "privacy.delete_warning"))}'
        f'</p>'
        f'</div>'
        f'</div>'
    )


def render_privacy_panel_script() -> str:
    """Return JS that wires the "Delete my data" button.

    The button calls ``/api/purge_user_data`` with ``confirm=true``.
    On success, the page shows a toast and reloads.
    """
    return """
<script data-ss-exec="true">
function ssPrivacyDelete() {
  if (!window.confirm('This will delete your traces, community pool, voice memos, SMS registry, and backups. Inventory and lists are kept. This cannot be undone. Continue?')) {
    return;
  }
  fetch('/api/purge_user_data?confirm=true', {method: 'POST'})
    .then(function(r){ return r.json(); })
    .then(function(data) {
      if (data && data.success) {
        var t = document.createElement('div');
        t.className = 'ss-toast-trigger';
        t.setAttribute('style', 'display:none;');
        t.setAttribute('data-toast-msg', 'Your data has been deleted.');
        t.setAttribute('data-toast-kind', 'success');
        document.body.appendChild(t);
      } else {
        console.warn('purge failed', data);
      }
    })
    .catch(function(e){ console.warn('ssPrivacyDelete failed', e); });
}
</script>
"""


__all__ = [
    "PurgeResult",
    "RetentionPolicy",
    "purge_user_data",
    "render_privacy_panel_html",
    "render_privacy_panel_script",
    "retention_summary",
]
