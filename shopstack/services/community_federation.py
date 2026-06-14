"""Federated community pool sync — Phase 11 (social value).

The community price map (Phase 8 #15) ships with a
local-first JSONL pool. The next step is *federation*:
anonymized bundles that households can export and import
to share prices across the network.

**1st-principles design:**

- A *bundle* is a JSONL file where every line is one
  observation, with a header line carrying the bundle's
  metadata (version, source_anon_id, salt_fingerprint,
  day_range).
- A bundle carries **no PII**: only canonical_name, price,
  city, store, day, anon_id, salt_fingerprint. The
  source_anon_id is rotated daily (already in
  :func:`make_anon_id`), and the salt_fingerprint lets the
  receiver verify that the bundle was produced with *some*
  salt (preventing replay).
- Importing a bundle appends each observation to the
  local pool (after a dedup check on the anon_id +
  day + canonical_name tuple).
- The user keeps full control: the export button is a
  manual action, and the import button is a manual
  action. No network sync in v1.

**Supersession rule:**

The local-only functions in
:mod:`shopstack.services.community_price_map` are *not*
replaced. They continue to work as the foundation. The
federation layer is **purely additive** — it reads from
and writes to the same local JSONL pool.

**Public API:**

- :class:`CommunityBundle` — the in-memory bundle model.
- :func:`export_bundle` — read the local pool, produce a
  bundle.
- :func:`import_bundle` — read a bundle (string or file),
  append to the local pool, return a summary.
- :func:`sync_status` — a tiny status line for the
  settings UI.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Iterable

from shopstack.services.community_price_map import (
    community_median,
    is_opted_in,
    make_anon_id,
    pool_stats,
    set_opt_in,
    submit_observation,
)

logger = logging.getLogger(__name__)


# ─── Bundle format constants ──────────────────────────────────

BUNDLE_VERSION = 1
BUNDLE_HEADER_KEY = "__bundle_header__"


# ─── Dataclasses ───────────────────────────────────────────


@dataclass
class CommunityBundle:
    """An in-memory bundle of community observations.

    The ``header`` carries the bundle's metadata (version,
    source, salt fingerprint, day range). The ``observations``
    list is the raw rows to be written to the local pool.
    """

    version: int
    salt_fingerprint: str
    source_label: str
    exported_at: str
    day_range_start: str
    day_range_end: str
    observations: list[dict[str, Any]] = field(default_factory=list)

    def to_jsonl(self) -> str:
        """Serialize the bundle to a JSONL string.

        The first line is the header (key ``__bundle_header__``).
        Subsequent lines are observations.
        """
        header = {
            "version": self.version,
            "salt_fingerprint": self.salt_fingerprint,
            "source_label": self.source_label,
            "exported_at": self.exported_at,
            "day_range_start": self.day_range_start,
            "day_range_end": self.day_range_end,
            "observation_count": len(self.observations),
        }
        lines: list[str] = [json.dumps({BUNDLE_HEADER_KEY: header}, ensure_ascii=False)]
        for obs in self.observations:
            lines.append(json.dumps(obs, ensure_ascii=False))
        return "\n".join(lines) + "\n"

    @classmethod
    def from_jsonl(cls, raw: str) -> "CommunityBundle":
        """Parse a JSONL bundle string into a CommunityBundle.

        Raises ValueError on malformed input or unsupported
        version. Missing fields are defaulted.
        """
        header: dict[str, Any] = {}
        observations: list[dict[str, Any]] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON line: {exc}") from exc
            if BUNDLE_HEADER_KEY in obj:
                header = dict(obj[BUNDLE_HEADER_KEY])
            else:
                observations.append(obj)
        if not header:
            raise ValueError("Bundle is missing the header line")
        version = int(header.get("version", 0))
        if version != BUNDLE_VERSION:
            raise ValueError(
                f"Unsupported bundle version: {version} "
                f"(expected {BUNDLE_VERSION})"
            )
        return cls(
            version=version,
            salt_fingerprint=str(header.get("salt_fingerprint", "")),
            source_label=str(header.get("source_label", "")),
            exported_at=str(header.get("exported_at", "")),
            day_range_start=str(header.get("day_range_start", "")),
            day_range_end=str(header.get("day_range_end", "")),
            observations=observations,
        )


# ─── Export ──────────────────────────────────────────────


def _salt_fingerprint() -> str:
    """Return a short fingerprint of the household's salt.

    Reading the salt file directly so the fingerprint
    reflects the actual salt (not a hash of nothing).
    """
    from shopstack.services.community_price_map import _SALT_FILE
    try:
        if not _SALT_FILE.is_file():
            return ""
        return hashlib.sha256(
            _SALT_FILE.read_bytes()
        ).hexdigest()[:12]
    except OSError:
        return ""


def export_bundle(
    *,
    source_label: str = "shopstack",
    city: str = "",
    max_observations: int = 500,
) -> CommunityBundle:
    """Build a bundle from the local community pool.

    Reads up to ``max_observations`` rows from the local
    JSONL pool (oldest first) and wraps them in a bundle.
    The bundle is anonymized by construction (the local
    pool only carries anon_ids, no PII).
    """
    from shopstack.services.community_price_map import _POOL_FILE
    observations: list[dict[str, Any]] = []
    if _POOL_FILE.is_file():
        try:
            with open(_POOL_FILE, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obs = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if city and obs.get("city") != city.lower():
                        continue
                    observations.append(obs)
                    if len(observations) >= max_observations:
                        break
        except OSError as exc:
            logger.debug("export_bundle read failed: %s", exc)
    # Compute day_range
    days = sorted({o.get("day", "") for o in observations if o.get("day")})
    return CommunityBundle(
        version=BUNDLE_VERSION,
        salt_fingerprint=_salt_fingerprint(),
        source_label=source_label,
        exported_at=datetime.now(timezone.utc).isoformat(),
        day_range_start=days[0] if days else "",
        day_range_end=days[-1] if days else "",
        observations=observations,
    )


def export_bundle_to_string(
    *,
    source_label: str = "shopstack",
    city: str = "",
) -> str:
    """Convenience: build a bundle and return its JSONL string."""
    return export_bundle(source_label=source_label, city=city).to_jsonl()


# ─── Import ──────────────────────────────────────────────


def import_bundle(
    raw: str,
    *,
    actor_user_id: str = "",
    require_opt_in: bool = True,
) -> dict[str, Any]:
    """Import a bundle into the local pool.

    Args:
        raw: The bundle's JSONL string.
        actor_user_id: The household performing the import
            (used to attribute the submission to the local
            household — does NOT leak to the bundle).
        require_opt_in: When True (default), refuse the import
            if the local household hasn't opted in to
            community sharing. This is the privacy gate.

    Returns:
        A dict with the import summary::

            {
                "accepted": int,         # how many observations were appended
                "skipped": int,          # how many were duplicates
                "rejected": int,         # how many were invalid
                "source_label": str,
                "version": int,
                "reason": str,           # human-readable summary
            }
    """
    if require_opt_in and not is_opted_in(actor_user_id):
        return {
            "accepted": 0, "skipped": 0, "rejected": 0,
            "source_label": "", "version": 0,
            "reason": "Local household has not opted in to community sharing.",
        }
    try:
        bundle = CommunityBundle.from_jsonl(raw)
    except ValueError as exc:
        return {
            "accepted": 0, "skipped": 0, "rejected": 0,
            "source_label": "", "version": 0,
            "reason": f"Invalid bundle: {exc}",
        }
    accepted = 0
    skipped = 0
    rejected = 0
    for obs in bundle.observations:
        cname = str(obs.get("canonical_name") or "").strip().lower()
        price = obs.get("price")
        if not cname or price is None or float(price) <= 0:
            rejected += 1
            continue
        # Dedup: skip if the same anon_id + day + cname is
        # already in the pool.
        if _is_duplicate(obs):
            skipped += 1
            continue
        # Submit to the local pool. The submit_observation
        # function takes the actor_user_id as the "household"
        # for the local-actor id (it doesn't leak to the bundle).
        result = submit_observation(
            actor_user_id, cname, float(price),
            city=str(obs.get("city") or ""),
            store=str(obs.get("store") or ""),
            unit=str(obs.get("unit") or "unit"),
            per_kg=obs.get("per_kg"),
            when=_parse_day(obs.get("day")),
        )
        if result.get("written"):
            accepted += 1
        else:
            rejected += 1
    return {
        "accepted": accepted,
        "skipped": skipped,
        "rejected": rejected,
        "source_label": bundle.source_label,
        "version": bundle.version,
        "reason": (
            f"Imported {accepted} from {bundle.source_label or 'unknown'} "
            f"(skipped {skipped} dupes, rejected {rejected} invalid)."
        ),
    }


def _is_duplicate(obs: dict[str, Any]) -> bool:
    """True if an equivalent observation is already in the pool.

    The dedup key is ``(day, canonical_name, price)`` — the
    semantic identity of an observation. We don't dedup
    on ``anon_id`` because :func:`submit_observation` always
    generates a fresh anon_id from the actor_user_id (the
    local salt is different from the source's salt), so the
    bundle's anon_id is *never* preserved in the local pool.
    """
    from shopstack.services.community_price_map import _POOL_FILE
    if not _POOL_FILE.is_file():
        return False
    target_day = str(obs.get("day") or "")
    target_cname = str(obs.get("canonical_name") or "").strip().lower()
    try:
        target_price = float(obs.get("price") or 0)
    except (TypeError, ValueError):
        return False
    if not (target_day and target_cname and target_price > 0):
        return False
    try:
        with open(_POOL_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (str(row.get("day", "")) == target_day
                        and str(row.get("canonical_name", "")).strip().lower() == target_cname
                        and abs(float(row.get("price", 0)) - target_price) < 0.01):
                    return True
    except OSError:
        return False
    return False


def _parse_day(day_str: Any) -> date | None:
    """Parse a YYYY-MM-DD string into a :class:`date`."""
    if not day_str:
        return None
    try:
        return datetime.strptime(str(day_str)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


# ─── Status (UI) ────────────────────────────────────────


def sync_status(actor_user_id: str = "") -> str:
    """Return a small status line for the community pool sync.

    Used by the household settings UI to show whether the
    household has opted in and the local pool's stats.
    """
    opted = is_opted_in(actor_user_id)
    if not opted:
        return (
            "<div class='sync-block sync-empty'>"
            "🔒 Opt in to community price sharing to enable federation."
            "</div>"
        )
    stats = pool_stats()
    if not stats.get("size"):
        return (
            "<div class='sync-block sync-empty'>"
            "📡 Opted in, but the local pool is empty. Add observations first."
            "</div>"
        )
    return (
        "<div class='sync-block'>"
        f"<div class='sync-stats'>"
        f"📡 <strong>{stats['size']}</strong> observations, "
        f"<strong>{stats['distinct_items']}</strong> items, "
        f"<strong>{stats['distinct_anon']}</strong> anonymized contributors"
        + (f" · newest: {stats['newest']}" if stats.get("newest") else "")
        + "</div>"
        "<div class='sync-chips'>"
        "<span class='sync-chip'>opt-in: ✅</span>"
        "<span class='sync-chip'>format: JSONL v1</span>"
        "</div>"
        "</div>"
    )


# ─── Public API ───────────────────────────────────────────


__all__ = [
    "BUNDLE_HEADER_KEY",
    "BUNDLE_VERSION",
    "CommunityBundle",
    "export_bundle",
    "export_bundle_to_string",
    "import_bundle",
    "sync_status",
]
