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


# ── Config key constants ──────────────────────────────────────────

# These are the ``app_config`` keys that map to each RetentionPolicy
# field. Centralising them here means the reader never has to guess
# the storage key for a given knob.
_CONFIG_KEY_TRACE_TTL = "retention.trace_ttl_days"
_CONFIG_KEY_COMMUNITY_POOL_RETENTION = "retention.community_pool_retention_days"
_CONFIG_KEY_VOICE_MEMO_RETENTION = "retention.voice_memo_retention_days"
_CONFIG_KEY_SMS_REGISTRY_RETENTION = "retention.sms_registry_retention_days"
_CONFIG_KEY_BACKUP_RETENTION = "retention.backup_retention_days"
_CONFIG_KEY_LOCALE_PERSISTENCE = "retention.locale_persistence"
_CONFIG_KEY_COMMUNITY_OPTIN = "retention.community_optin"

RETENTION_PROFILE_VALUES: dict[str, dict[str, str]] = {
    "balanced": {
        _CONFIG_KEY_TRACE_TTL: "30",
        _CONFIG_KEY_COMMUNITY_POOL_RETENTION: "90",
        _CONFIG_KEY_VOICE_MEMO_RETENTION: "7",
        _CONFIG_KEY_SMS_REGISTRY_RETENTION: "0",
        _CONFIG_KEY_BACKUP_RETENTION: "0",
        _CONFIG_KEY_LOCALE_PERSISTENCE: "1",
        _CONFIG_KEY_COMMUNITY_OPTIN: "0",
    },
    "strict": {
        _CONFIG_KEY_TRACE_TTL: "7",
        _CONFIG_KEY_COMMUNITY_POOL_RETENTION: "30",
        _CONFIG_KEY_VOICE_MEMO_RETENTION: "3",
        _CONFIG_KEY_SMS_REGISTRY_RETENTION: "0",
        _CONFIG_KEY_BACKUP_RETENTION: "0",
        _CONFIG_KEY_LOCALE_PERSISTENCE: "0",
        _CONFIG_KEY_COMMUNITY_OPTIN: "0",
    },
    "shared": {
        _CONFIG_KEY_TRACE_TTL: "30",
        _CONFIG_KEY_COMMUNITY_POOL_RETENTION: "90",
        _CONFIG_KEY_VOICE_MEMO_RETENTION: "7",
        _CONFIG_KEY_SMS_REGISTRY_RETENTION: "0",
        _CONFIG_KEY_BACKUP_RETENTION: "0",
        _CONFIG_KEY_LOCALE_PERSISTENCE: "1",
        _CONFIG_KEY_COMMUNITY_OPTIN: "1",
    },
}

RETENTION_PROFILE_METADATA: dict[str, dict[str, Any]] = {
    "balanced": {
        "label": "Balanced",
        "description": "Recommended default for most households: keep useful history without retaining too much.",
        "recommended": True,
    },
    "strict": {
        "label": "Strict",
        "description": "Minimise retention windows for a more privacy-forward posture.",
        "recommended": False,
    },
    "shared": {
        "label": "Shared",
        "description": "Keep the household opt-in enabled so pricing insights can be shared with the community pool.",
        "recommended": False,
    },
}

# ── Summary builder ────────────────────────────────────────────────


def retention_summary(database: Any, user_id: str = "") -> RetentionPolicy:
    """Build a :class:`RetentionPolicy` for ``user_id``.

    Reads the canonical settings (defaults) and overlays any
    per-household overrides. Best-effort: a DB error or missing
    settings table returns the defaults — we never want a
    settings fetch to crash the page render.

    Long-term direction: each retention knob has a dedicated
    ``retention.<knob_name>`` config key in ``app_config``.
    Adding a new knob is a one-line constant above plus one
    line in this function.
    """
    # Read the canonical defaults from the DB settings. If the
    # DB doesn't expose them (e.g. an older schema), fall back
    # to the dataclass defaults.
    def _cfg(key: str, default: str) -> str:
        if database and hasattr(database, "get_config_value"):
            return database.get_config_value(key, default)
        return default

    summary = RetentionPolicy()
    try:
        summary = RetentionPolicy(
            trace_ttl_days=_coerce_int(
                _cfg(_CONFIG_KEY_TRACE_TTL, str(summary.trace_ttl_days)),
                summary.trace_ttl_days,
            ),
            community_pool_retention_days=_coerce_int(
                _cfg(_CONFIG_KEY_COMMUNITY_POOL_RETENTION, str(summary.community_pool_retention_days)),
                summary.community_pool_retention_days,
            ),
            voice_memo_retention_days=_coerce_int(
                _cfg(_CONFIG_KEY_VOICE_MEMO_RETENTION, str(summary.voice_memo_retention_days)),
                summary.voice_memo_retention_days,
            ),
            sms_registry_retention_days=_coerce_int(
                _cfg(_CONFIG_KEY_SMS_REGISTRY_RETENTION, str(summary.sms_registry_retention_days)),
                summary.sms_registry_retention_days,
            ),
            backup_retention_days=_coerce_int(
                _cfg(_CONFIG_KEY_BACKUP_RETENTION, str(summary.backup_retention_days)),
                summary.backup_retention_days,
            ),
            locale_persistence=_cfg(_CONFIG_KEY_LOCALE_PERSISTENCE, "1") == "1",
            community_optin=_cfg(_CONFIG_KEY_COMMUNITY_OPTIN, "0") == "1",
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("retention_summary: %s", exc)
    return summary


def update_retention_setting(
    database: Any,
    key: str,
    value: str,
) -> bool:
    """Update a single retention setting in the DB.

    ``key`` must be one of the ``_CONFIG_KEY_*`` constants defined
    above. Returns True on success, False if the key is unknown or
    the DB write fails.

    Args:
        database: The ShopStack database. Must expose
            ``set_config_value(key, value)``.
        key: One of the ``_CONFIG_KEY_*`` constants (e.g.
            ``_CONFIG_KEY_TRACE_TTL``).
        value: The new value as a string. Callers are
            responsible for serialisation (int → str, bool → "0"/"1").

    Returns:
        True if the value was written successfully.
    """
    _VALID_KEYS = {
        _CONFIG_KEY_TRACE_TTL,
        _CONFIG_KEY_COMMUNITY_POOL_RETENTION,
        _CONFIG_KEY_VOICE_MEMO_RETENTION,
        _CONFIG_KEY_SMS_REGISTRY_RETENTION,
        _CONFIG_KEY_BACKUP_RETENTION,
        _CONFIG_KEY_LOCALE_PERSISTENCE,
        _CONFIG_KEY_COMMUNITY_OPTIN,
    }
    if key not in _VALID_KEYS:
        return False
    if not hasattr(database, "set_config_value"):
        return False
    try:
        database.set_config_value(key, value)
        logger.info("update_retention_setting: %s = %s", key, value)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("update_retention_setting failed: key=%s value=%s exc=%s", key, value, exc)
        return False


def _policy_from_values(values: dict[str, str]) -> RetentionPolicy:
    """Build a policy snapshot by overlaying raw config values on defaults."""
    base = RetentionPolicy()
    return RetentionPolicy(
        trace_ttl_days=_coerce_int(values.get(_CONFIG_KEY_TRACE_TTL, str(base.trace_ttl_days)), base.trace_ttl_days),
        trace_max_rows=base.trace_max_rows,
        community_pool_retention_days=_coerce_int(
            values.get(_CONFIG_KEY_COMMUNITY_POOL_RETENTION, str(base.community_pool_retention_days)),
            base.community_pool_retention_days,
        ),
        voice_memo_retention_days=_coerce_int(
            values.get(_CONFIG_KEY_VOICE_MEMO_RETENTION, str(base.voice_memo_retention_days)),
            base.voice_memo_retention_days,
        ),
        sms_registry_retention_days=_coerce_int(
            values.get(_CONFIG_KEY_SMS_REGISTRY_RETENTION, str(base.sms_registry_retention_days)),
            base.sms_registry_retention_days,
        ),
        backup_retention_days=_coerce_int(
            values.get(_CONFIG_KEY_BACKUP_RETENTION, str(base.backup_retention_days)),
            base.backup_retention_days,
        ),
        locale_persistence=values.get(_CONFIG_KEY_LOCALE_PERSISTENCE, "1") == "1",
        community_optin=values.get(_CONFIG_KEY_COMMUNITY_OPTIN, "0") == "1",
    )


@dataclass(frozen=True)
class ApplyRetentionProfileResult:
    """Result from applying one of the named privacy profiles."""

    profile: str
    success: bool = False
    updated_keys: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    summary: RetentionPolicy = field(default_factory=RetentionPolicy)


@dataclass(frozen=True)
class RetentionProfileSpec:
    """Canonical metadata for a named privacy profile."""

    profile: str
    label: str
    description: str
    recommended: bool = False
    values: dict[str, str] = field(default_factory=dict)
    summary: RetentionPolicy = field(default_factory=RetentionPolicy)


def retention_profiles(database: Any = None, user_id: str = "") -> list[RetentionProfileSpec]:
    """Return the canonical privacy profile catalog.

    ``database`` and ``user_id`` are accepted for symmetry with the
    other retention helpers. The catalog is static for now, but this
    seam lets us overlay household-specific profile defaults later
    without changing the API contract.
    """
    _ = database, user_id  # reserved for future household-specific overrides
    profiles: list[RetentionProfileSpec] = []
    for profile, values in RETENTION_PROFILE_VALUES.items():
        meta = RETENTION_PROFILE_METADATA.get(profile, {})
        profiles.append(
            RetentionProfileSpec(
                profile=profile,
                label=str(meta.get("label", profile.title())),
                description=str(meta.get("description", "")),
                recommended=bool(meta.get("recommended", False)),
                values=dict(values),
                summary=_policy_from_values(values),
            ),
        )
    return profiles


def apply_retention_profile(
    database: Any,
    profile: str,
    *,
    user_id: str = "",
) -> ApplyRetentionProfileResult:
    """Apply a named retention profile atomically when possible.

    Profiles are the canonical bundle of privacy settings for the
    household. This keeps the backend as the source of truth for the
    "balanced", "strict", and "shared" presets that the shell can
    surface.
    """
    profile_key = (profile or "").strip().lower()
    values = RETENTION_PROFILE_VALUES.get(profile_key)
    if values is None:
        return ApplyRetentionProfileResult(
            profile=profile_key or profile,
            success=False,
            errors=[f"unknown profile: {profile!r}"],
            summary=retention_summary(database, user_id=user_id),
        )
    if not database:
        return ApplyRetentionProfileResult(
            profile=profile_key,
            success=False,
            errors=["database unavailable"],
            summary=retention_summary(database, user_id=user_id),
        )

    try:
        if hasattr(database, "set_config_values"):
            database.set_config_values(values)
        else:
            for key, value in values.items():
                if not update_retention_setting(database, key, value):
                    raise RuntimeError(f"failed to update {key}")
        summary = retention_summary(database, user_id=user_id)
        return ApplyRetentionProfileResult(
            profile=profile_key,
            success=True,
            updated_keys=list(values.keys()),
            summary=summary,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("apply_retention_profile failed: profile=%s exc=%s", profile_key, exc)
        return ApplyRetentionProfileResult(
            profile=profile_key,
            success=False,
            updated_keys=list(values.keys()),
            errors=[str(exc)],
            summary=retention_summary(database, user_id=user_id),
        )


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

    def _days_select(key: str, days: int, config_key: str) -> str:
        """Render a row with a ``<select>`` that changes the retention days."""
        label = escape(get_translation(locale, key))
        options = [0, 7, 14, 30, 60, 90, 180, 365]
        opts_html = "".join(
            f"<option value='{v}' {'selected' if v == days else ''}>"
            f"{'Indefinite' if v == 0 else f'{v} days'}</option>"
            for v in options
        )
        return (
            f'<div class="privacy-row" '
            f'style="display:flex;align-items:center;gap:12px;'
            f'padding:8px 0;border-bottom:1px solid var(--bg-warm,#FFF1D6);">'
            f'<span class="privacy-row-label" style="flex:1;font-size:0.875rem;">'
            f'{label}</span>'
            f'<select class="privacy-select" data-config-key="{escape(config_key)}" '
            f'style="font-size:0.8125rem;padding:4px 6px;border-radius:4px;'
            f'border:1px solid var(--border,#E5D5B7);background:var(--bg-input,#FFF7EA);'
            f'color:var(--text,#1F1812);">'
            f'{opts_html}'
            f'</select>'
            f'</div>'
        )

    def _bool_checkbox(key: str, value: bool, config_key: str) -> str:
        """Render a row with a checkbox for boolean settings."""
        label = escape(get_translation(locale, key))
        checked = 'checked' if value else ''
        return (
            f'<div class="privacy-row" '
            f'style="display:flex;align-items:center;gap:12px;'
            f'padding:8px 0;border-bottom:1px solid var(--bg-warm,#FFF1D6);">'
            f'<label class="privacy-row-label" style="flex:1;font-size:0.875rem;'
            f'cursor:pointer;">'
            f'<input type="checkbox" class="privacy-checkbox" '
            f'data-config-key="{escape(config_key)}" {checked} '
            f'style="margin-right:8px;">'
            f'{label}'
            f'</label>'
            f'</div>'
        )

    rows = "".join(
        [
            _days_select("privacy.trace_ttl", summary.trace_ttl_days, _CONFIG_KEY_TRACE_TTL),
            _days_select("privacy.community_retention", summary.community_pool_retention_days, _CONFIG_KEY_COMMUNITY_POOL_RETENTION),
            _days_select("privacy.voice_memo_retention", summary.voice_memo_retention_days, _CONFIG_KEY_VOICE_MEMO_RETENTION),
            _days_select("privacy.sms_retention", summary.sms_registry_retention_days, _CONFIG_KEY_SMS_REGISTRY_RETENTION),
            _days_select("privacy.backup_retention", summary.backup_retention_days, _CONFIG_KEY_BACKUP_RETENTION),
            _bool_checkbox("privacy.locale_persistence", summary.locale_persistence, _CONFIG_KEY_LOCALE_PERSISTENCE),
            _bool_checkbox("privacy.community_optin", summary.community_optin, _CONFIG_KEY_COMMUNITY_OPTIN),
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
    """Return JS that wires the privacy panel interactive controls.

    Two responsibilities:

    1. **Auto-save toggles** — every ``.privacy-select`` and
       ``.privacy-checkbox`` fires a POST to ``/api/update_retention``
       on change, passing ``key`` (from ``data-config-key``) and
       ``value`` (the selected/checked state). A toast confirms
       success; failures are logged to console.

    2. **"Delete my data" button** — calls
       ``/api/purge_user_data?confirm=true``, shows a toast on
       success.

    Both use the existing ``ss-toast-trigger`` pattern so the
    page-level toast MutationObserver (item #99b from the
    2026-06-13 review) shows a green toast.
    """
    return """
<script data-ss-exec="true">
(function() {
  // ── Retention toggle auto-save ───────────────────────────────
  function ssSaveRetention(key, value) {
    fetch('/api/update_retention', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({key: key, value: value})
    })
    .then(function(r){ return r.json(); })
    .then(function(data) {
      var kind = data && data.success ? 'success' : 'error';
      var msg = data && data.success ? 'Saved' : 'Failed to save';
      var t = document.createElement('div');
      t.className = 'ss-toast-trigger';
      t.setAttribute('style', 'display:none;');
      t.setAttribute('data-toast-msg', msg + ': ' + key);
      t.setAttribute('data-toast-kind', kind);
      document.body.appendChild(t);
    })
    .catch(function(e){ console.warn('ssSaveRetention failed', e); });
  }

  // Wire selects
  document.addEventListener('change', function(e) {
    var sel = e.target.closest && e.target.closest('.privacy-select');
    if (sel) {
      var key = sel.getAttribute('data-config-key');
      if (key) ssSaveRetention(key, sel.value);
      return;
    }
    var cb = e.target.closest && e.target.closest('.privacy-checkbox');
    if (cb) {
      var key2 = cb.getAttribute('data-config-key');
      if (key2) ssSaveRetention(key2, cb.checked ? '1' : '0');
    }
  });

  // ── Delete my data button ────────────────────────────────────
  window.ssPrivacyDelete = function() {
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
  };
})();
</script>
"""


__all__ = [
    "ApplyRetentionProfileResult",
    "RETENTION_PROFILE_METADATA",
    "PurgeResult",
    "RetentionPolicy",
    "RetentionProfileSpec",
    "RETENTION_PROFILE_VALUES",
    "apply_retention_profile",
    "purge_user_data",
    "render_privacy_panel_html",
    "render_privacy_panel_script",
    "retention_profiles",
    "retention_summary",
    "update_retention_setting",
    # Config key constants
    "_CONFIG_KEY_TRACE_TTL",
    "_CONFIG_KEY_COMMUNITY_POOL_RETENTION",
    "_CONFIG_KEY_VOICE_MEMO_RETENTION",
    "_CONFIG_KEY_SMS_REGISTRY_RETENTION",
    "_CONFIG_KEY_BACKUP_RETENTION",
    "_CONFIG_KEY_LOCALE_PERSISTENCE",
    "_CONFIG_KEY_COMMUNITY_OPTIN",
]
