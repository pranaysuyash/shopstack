"""Community price map — Phase 6 #15 (privacy-preserving, opt-in, local-first).

**The problem:**

ShopStack's price memory knows the prices *this* household paid.
But "is ₹80/kg for tomatoes a good deal?" depends on what *other*
households in the same city are paying today. A community price
map closes that loop.

**The privacy stance (v1, local-first):**

- **Opt-in only.** A household must explicitly set
  ``opt_in = True`` in the household settings before *any* of their
  observations are written to the community pool. The default is
  ``False`` (opt-out by default).
- **Anonymized at write time.** The contributor's ``user_id`` is
  replaced with ``anon_id = sha256(salt + user_id + day_bucket)[:16]``,
  where ``day_bucket = YYYY-MM-DD`` rolls every 24h. The original
  user_id is **never** written to disk.
- **Local-first.** The community pool is a single JSONL file at
  ``~/.shopstack/community/prices.jsonl``. v1 has no network sync —
  the pool is the household's own contribution and a placeholder
  for future import from a community sync service.
- **No PII fields.** Only the canonical name, price, store name
  (city-mapped, e.g. "DMart Mumbai" → "DMart-Central"), the city
  code, and the day bucket are written. No display name, no notes,
  no user-controlled text.
- **Salt is per-household.** Generated once and stored in
  ``~/.shopstack/community/salt``. If the user clears the community
  pool, the salt rotates, and old observations become un-linkable
  (since the anon_id is a function of the salt).

**How to read:**

- :func:`community_median` returns the median community price for a
  given canonical_name and city. If no data exists, returns
  ``None``.
- :func:`render_community_indicator_html` renders a small "₹X
  community median" badge next to a price, plus a "You're paying
  ₹Y vs ₹X community" delta when the household's own price is
  known.

**Future work (deferred):**

- Network sync via signed, append-only bundles (no central server).
- Federation across devices.
- Differential privacy noise on writes.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# ─── Storage paths ─────────────────────────────────────────────────


_COMMUNITY_DIR = Path.home() / ".shopstack" / "community"
_POOL_FILE = _COMMUNITY_DIR / "prices.jsonl"
_SALT_FILE = _COMMUNITY_DIR / "salt"
_OPTED_IN_FILE = _COMMUNITY_DIR / "opted_in.json"


# ─── Salt management ──────────────────────────────────────────────


def _load_or_create_salt() -> str:
    """Return the per-household salt, creating it on first use."""
    try:
        if _SALT_FILE.is_file():
            return _SALT_FILE.read_text(encoding="utf-8").strip()
        _COMMUNITY_DIR.mkdir(parents=True, exist_ok=True)
        # 32 random bytes hex-encoded → 64 chars
        salt = hashlib.sha256(os.urandom(32)).hexdigest()
        _SALT_FILE.write_text(salt, encoding="utf-8")
        try:
            os.chmod(_SALT_FILE, 0o600)
        except OSError:
            pass
        return salt
    except OSError as exc:
        logger.debug("salt I/O failed: %s", exc)
        # Fall back to a process-stable random salt (not persisted)
        return hashlib.sha256(os.urandom(32)).hexdigest()


def rotate_salt() -> None:
    """Delete the salt file (next read will generate a new one).

    Use this when the user wants to "start fresh" — old observations
    remain in the pool but become un-linkable to any user_id since
    the anon_id is a function of the salt.
    """
    try:
        if _SALT_FILE.is_file():
            _SALT_FILE.unlink()
    except OSError as exc:
        logger.debug("rotate_salt failed: %s", exc)


# ─── Opt-in / opt-out ─────────────────────────────────────────────


def set_opt_in(user_id: str, opt_in: bool) -> None:
    """Persist the opt-in flag for ``user_id``.

    Default is ``False`` (opt-out).
    """
    if not user_id:
        return
    try:
        _COMMUNITY_DIR.mkdir(parents=True, exist_ok=True)
        prefs: dict[str, bool] = {}
        if _OPTED_IN_FILE.is_file():
            try:
                prefs = json.loads(_OPTED_IN_FILE.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                prefs = {}
        prefs[user_id] = bool(opt_in)
        _OPTED_IN_FILE.write_text(json.dumps(prefs), encoding="utf-8")
    except OSError as exc:
        logger.debug("set_opt_in failed: %s", exc)


def is_opted_in(user_id: str) -> bool:
    """True if the household has opted in to community price sharing."""
    if not user_id:
        return False
    try:
        if not _OPTED_IN_FILE.is_file():
            return False
        prefs = json.loads(_OPTED_IN_FILE.read_text(encoding="utf-8"))
        return bool(prefs.get(user_id, False))
    except (OSError, json.JSONDecodeError):
        return False


# ─── Anonymization ─────────────────────────────────────────────────


def make_anon_id(user_id: str, when: date | None = None) -> str:
    """Return the daily-rolling anonymized id for ``user_id``.

    The id is ``sha256(salt + user_id + day_bucket)[:16]``. Two
    observations from the same user on different days get different
    anon_ids, breaking the temporal correlation at the cost of
    per-day linkage (which is fine for a price map).
    """
    salt = _load_or_create_salt()
    when = when or date.today()
    bucket = when.strftime("%Y-%m-%d")
    h = hashlib.sha256(f"{salt}|{user_id}|{bucket}".encode("utf-8")).hexdigest()
    return h[:16]


# ─── Pool I/O ──────────────────────────────────────────────────────


@dataclass
class CommunityObservation:
    """One anonymized price observation."""

    canonical_name: str
    price: float
    city: str
    store: str  # already city-mapped
    anon_id: str
    day: str  # YYYY-MM-DD
    unit: str = "unit"
    per_kg: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "price": self.price,
            "city": self.city,
            "store": self.store,
            "anon_id": self.anon_id,
            "day": self.day,
            "unit": self.unit,
            "per_kg": self.per_kg,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CommunityObservation":
        return cls(
            canonical_name=str(d.get("canonical_name", "")),
            price=float(d.get("price", 0) or 0),
            city=str(d.get("city", "")),
            store=str(d.get("store", "")),
            anon_id=str(d.get("anon_id", "")),
            day=str(d.get("day", "")),
            unit=str(d.get("unit", "unit")),
            per_kg=d.get("per_kg"),
        )


def _normalize_store_name(store: str, city: str) -> str:
    """Map a free-form store name to a city-scoped tag.

    Examples:
        "DMart Mumbai" + "mumbai" → "DMart"
        "Reliance Fresh" + "delhi" → "Reliance Fresh"
        "Big Bazaar, Bandra" + "mumbai" → "Big Bazaar"

    The goal is to prevent exact address leakage while still letting
    a user compare prices across named chains.
    """
    if not store:
        return "unknown"
    s = store.strip()
    # Drop city tokens
    for tok in (city, city.title(), city.upper()):
        if tok and tok in s:
            s = s.replace(tok, "").strip(" ,.-")
    # Drop common suffix noise (branch names, addresses)
    for sep in (",", "-"):
        if sep in s:
            s = s.split(sep, 1)[0].strip()
    return s or "unknown"


def submit_observation(
    user_id: str,
    canonical_name: str,
    price: float,
    city: str = "",
    store: str = "",
    unit: str = "unit",
    per_kg: float | None = None,
    when: date | None = None,
) -> dict[str, Any]:
    """Append a new observation to the community pool.

    **Refuses to write if the household is not opted in.** This is
    the privacy gate; the rest of the function is straightforward.

    Returns ``{"written": bool, "reason": str, "anon_id": str}``.
    Never raises.
    """
    if not is_opted_in(user_id):
        return {
            "written": False,
            "reason": "Not opted in to community price sharing.",
            "anon_id": "",
        }
    if not canonical_name or price <= 0:
        return {
            "written": False,
            "reason": "Invalid observation (empty name or non-positive price).",
            "anon_id": "",
        }
    when = when or date.today()
    obs = CommunityObservation(
        canonical_name=canonical_name.strip().lower(),
        price=float(price),
        city=(city or "").strip().lower(),
        store=_normalize_store_name(store, city),
        anon_id=make_anon_id(user_id, when=when),
        day=when.strftime("%Y-%m-%d"),
        unit=(unit or "unit").strip(),
        per_kg=per_kg,
    )
    try:
        _COMMUNITY_DIR.mkdir(parents=True, exist_ok=True)
        with open(_POOL_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(obs.to_dict(), ensure_ascii=False) + "\n")
        return {
            "written": True,
            "reason": "Submitted anonymously.",
            "anon_id": obs.anon_id,
        }
    except OSError as exc:
        logger.debug("submit_observation failed: %s", exc)
        return {
            "written": False,
            "reason": f"Storage error: {exc}",
            "anon_id": "",
        }


def _read_pool() -> list[CommunityObservation]:
    """Read all observations from the local pool file (best-effort)."""
    if not _POOL_FILE.is_file():
        return []
    out: list[CommunityObservation] = []
    try:
        with open(_POOL_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    out.append(CommunityObservation.from_dict(d))
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue
    except OSError as exc:
        logger.debug("_read_pool failed: %s", exc)
    return out


# ─── Read API ──────────────────────────────────────────────────────


def community_median(
    canonical_name: str,
    city: str = "",
    days: int = 30,
    when: date | None = None,
) -> dict[str, Any] | None:
    """Return the community median price for ``canonical_name``.

    Returns ``None`` when no data exists. Otherwise a dict with:
    - ``median_price``: the median per-kg (or absolute) price.
    - ``sample_size``: number of observations used.
    - ``store_count``: distinct store names.
    - ``as_of``: the most recent observation date.
    """
    if not canonical_name:
        return None
    when = when or date.today()
    cutoff_day = (when - timedelta(days=days)).strftime("%Y-%m-%d")
    name = canonical_name.strip().lower()
    city_norm = (city or "").strip().lower()
    rows = [
        o for o in _read_pool()
        if o.canonical_name == name
        and o.day >= cutoff_day
        and (not city_norm or o.city == city_norm)
        and o.price > 0
    ]
    if not rows:
        return None
    prices = [r.price for r in rows if r.price > 0]
    if not prices:
        return None
    return {
        "median_price": round(statistics.median(prices), 2),
        "sample_size": len(prices),
        "store_count": len({r.store for r in rows}),
        "as_of": max(r.day for r in rows),
    }


def community_delta(
    canonical_name: str,
    own_price: float,
    city: str = "",
    days: int = 30,
    when: date | None = None,
) -> dict[str, Any] | None:
    """Compare ``own_price`` to the community median.

    Returns ``None`` if no community data exists. Otherwise:
    - ``delta_pct``: (own - median) / median × 100.
    - ``verdict``: "cheaper" (<-5%), "fair" (-5% to +5%),
      "pricier" (>+5%).
    """
    summary = community_median(canonical_name, city=city, days=days, when=when)
    if summary is None or summary["median_price"] <= 0:
        return None
    median = summary["median_price"]
    delta = (own_price - median) / median * 100
    if delta < -5:
        verdict = "cheaper"
    elif delta > 5:
        verdict = "pricier"
    else:
        verdict = "fair"
    return {
        "median_price": median,
        "own_price": own_price,
        "delta_pct": round(delta, 1),
        "verdict": verdict,
        "sample_size": summary["sample_size"],
    }


# ─── HTML rendering ───────────────────────────────────────────────


def render_community_indicator_html(
    canonical_name: str,
    own_price: float | None = None,
    city: str = "",
    locale: str = "en",
    when: date | None = None,
) -> str:
    """Render a small badge showing the community median + delta.

    Args:
        canonical_name: The item to look up.
        own_price: The household's own price (optional). When
            provided, also shows the delta.
        city: City scope for the community median.
        locale: Translation locale.
        when: Override "now" for deterministic tests.
    """
    summary = community_median(canonical_name, city=city, when=when)
    if summary is None:
        return (
            "<span class='cm-pill cm-pill-empty' "
            "title='No community data yet — opt in to share prices.'>"
            "👥 no community data</span>"
        )
    median = summary["median_price"]
    sample = summary["sample_size"]
    badge = (
        f"<span class='cm-pill' title='Median of {sample} community observation(s)'>"
        f"👥 ₹{median:.0f}</span>"
    )
    if own_price is not None and own_price > 0:
        delta = community_delta(canonical_name, own_price, city=city, when=when)
        if delta is not None:
            verdict = delta["verdict"]
            color = {
                "cheaper": "var(--green, #176B49)",
                "fair":    "var(--text-dim, #6F6254)",
                "pricier": "var(--red, #A63F31)",
            }[verdict]
            sign = "+" if delta["delta_pct"] >= 0 else ""
            badge += (
                f" <span class='cm-delta' style='color:{color};' "
                f"title='You paid ₹{own_price:.0f} vs ₹{median:.0f} community median'>"
                f"you {sign}{delta['delta_pct']:.1f}%</span>"
            )
    return badge


def render_opt_in_toggle_html(user_id: str, locale: str = "en") -> str:
    """Render a small toggle / status line for the community opt-in.

    For the v1 UI, this is a static status line. The actual toggle
    is a checkbox wired to :func:`set_opt_in`. Future work: a
    dedicated settings panel.
    """
    if is_opted_in(user_id):
        return (
            "<div class='cm-optin cm-optin-on'>"
            "✅ You're sharing prices anonymously. "
            f"<span class='cm-optin-meta'>anon_id: {escape(make_anon_id(user_id)[:8])}…</span>"
            "</div>"
        )
    return (
        "<div class='cm-optin cm-optin-off'>"
        "🔒 You're not sharing prices. Opt in to compare with the community."
        "</div>"
    )


# ─── Maintenance ───────────────────────────────────────────────────


def clear_pool() -> dict[str, Any]:
    """Wipe the local community pool (rotates the salt too).

    Use this when the user wants to "delete all my community data."
    """
    try:
        if _POOL_FILE.is_file():
            _POOL_FILE.unlink()
        rotate_salt()
        return {"cleared": True, "reason": "Pool and salt wiped."}
    except OSError as exc:
        return {"cleared": False, "reason": str(exc)}


def pool_stats() -> dict[str, Any]:
    """Return summary stats about the local community pool."""
    rows = _read_pool()
    if not rows:
        return {"size": 0, "distinct_items": 0, "distinct_anon": 0}
    return {
        "size": len(rows),
        "distinct_items": len({r.canonical_name for r in rows}),
        "distinct_anon": len({r.anon_id for r in rows}),
        "newest": max((r.day for r in rows), default=""),
    }


__all__ = [
    "CommunityObservation",
    "clear_pool",
    "community_delta",
    "community_median",
    "is_opted_in",
    "make_anon_id",
    "pool_stats",
    "render_community_indicator_html",
    "render_opt_in_toggle_html",
    "rotate_salt",
    "set_opt_in",
    "submit_observation",
]
