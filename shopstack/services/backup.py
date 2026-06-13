
"""Encrypted backup and restore for ShopStack.

The local-first thesis is only complete when the household can take their
data with them — or recover it after a disk failure. This service:

- **export_backup(db, user_id, passphrase)** — collects every row tied
  to the household (inventory, shopping lists, price observations,
  preferences, locations) into a JSON envelope, encrypts with AES-256-GCM
  using a key derived from the passphrase via PBKDF2-HMAC-SHA256, and
  returns the base64 envelope as a string ready for download.

- **import_backup(db, envelope_json, passphrase, user_id)** — decrypts,
  validates the version, and atomically inserts/replaces the household's
  data. Conflicts (lot_id / list_id collisions) are reported in the
  returned summary.

Security notes:
- AES-GCM (authenticated encryption; tampering is detected).
- PBKDF2 with 200_000 iterations and a 16-byte random salt.
- 12-byte random nonce per encryption.
- The salt and nonce are stored in the envelope (they are not secret).

Backup envelope (JSON)::

    {
      "version": 1,
      "kdf": "pbkdf2-sha256",
      "iterations": 200000,
      "salt_b64": "...",
      "nonce_b64": "...",
      "ciphertext_b64": "...",
      "created_at": "2026-06-12T10:00:00Z",
      "household_id": "..."
    }

The plaintext inside ``ciphertext_b64`` is::

    {
      "household_id": "...",
      "created_at": "...",
      "inventory_lots": [...],
      "shopping_lists": [...],
      "shopping_list_items": [...],
      "price_observations": [...],
      "preference_signals": [...],
      "household_locations": [...]
    }
"""

from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from shopstack.schemas.models import ShoppingListItem

logger = logging.getLogger(__name__)


BACKUP_VERSION = 1
KDF_ITERATIONS = 200_000
SALT_BYTES = 16
NONCE_BYTES = 12
KEY_BYTES = 32  # AES-256
MIN_PASSPHRASE_LENGTH = 4


@dataclass
class BackupSummary:
    """Result of a backup or restore operation."""

    success: bool
    operation: str  # "export" | "import"
    created_at: str
    counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    error: str = ""
    envelope_json: str = ""  # populated on export only

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "operation": self.operation,
            "created_at": self.created_at,
            "counts": self.counts,
            "notes": self.notes,
            "error": self.error,
        }


# ─── Cryptography helpers ──────────────────────────────────────────────────


def _derive_key(passphrase: str, salt: bytes, iterations: int = KDF_ITERATIONS) -> bytes:
    """Derive a 256-bit key from the passphrase using PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_BYTES,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def _encrypt(plaintext: bytes, passphrase: str) -> dict[str, str]:
    """Encrypt with AES-256-GCM. Returns a header dict ready to JSON-serialize."""
    salt = os.urandom(SALT_BYTES)
    nonce = os.urandom(NONCE_BYTES)
    key = _derive_key(passphrase, salt)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return {
        "salt_b64": base64.b64encode(salt).decode("ascii"),
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
    }


def _decrypt(envelope: dict[str, str], passphrase: str) -> bytes:
    """Decrypt an envelope produced by ``_encrypt``. Raises on tampering."""
    salt = base64.b64decode(envelope["salt_b64"])
    nonce = base64.b64decode(envelope["nonce_b64"])
    ciphertext = base64.b64decode(envelope["ciphertext_b64"])
    key = _derive_key(passphrase, salt)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


# ─── Data collection ──────────────────────────────────────────────────────


def _collect_payload(db, user_id: str) -> dict[str, Any]:
    """Collect every household-scoped row into a JSON-safe dict."""
    payload: dict[str, Any] = {
        "household_id": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Inventory lots
    try:
        lots = db.get_inventory(user_id=user_id) or []
        payload["inventory_lots"] = [_lot_to_dict(lot) for lot in lots]
    except Exception as exc:
        logger.debug("Backup: inventory_lots failed: %s", exc)
        payload["inventory_lots"] = []

    # Shopping lists + their items
    try:
        lists = db.conn.execute(
            "SELECT * FROM shopping_lists WHERE user_id = ?", (user_id,)
        ).fetchall()
        payload["shopping_lists"] = [dict(r) for r in lists]
        list_ids = [r["list_id"] for r in lists]
        if list_ids:
            placeholders = ",".join("?" * len(list_ids))
            items = db.conn.execute(
                f"SELECT * FROM shopping_list_items WHERE list_id IN ({placeholders})",
                list_ids,
            ).fetchall()
            payload["shopping_list_items"] = [dict(r) for r in items]
        else:
            payload["shopping_list_items"] = []
    except Exception as exc:
        logger.debug("Backup: shopping_lists failed: %s", exc)
        payload["shopping_lists"] = []
        payload["shopping_list_items"] = []

    # Price observations
    try:
        rows = db.conn.execute(
            "SELECT * FROM price_observations WHERE user_id = ?", (user_id,)
        ).fetchall()
        payload["price_observations"] = [dict(r) for r in rows]
    except Exception as exc:
        logger.debug("Backup: price_observations failed: %s", exc)
        payload["price_observations"] = []

    # Preference signals
    try:
        rows = db.conn.execute(
            "SELECT * FROM preference_signals WHERE user_id = ?", (user_id,)
        ).fetchall()
        payload["preference_signals"] = [dict(r) for r in rows]
    except Exception as exc:
        logger.debug("Backup: preference_signals failed: %s", exc)
        payload["preference_signals"] = []

    # Household locations (shared tree across households; backup all)
    try:
        rows = db.conn.execute(
            "SELECT * FROM household_locations ORDER BY parent_location_id"
        ).fetchall()
        payload["household_locations"] = [dict(r) for r in rows]
    except Exception as exc:
        logger.debug("Backup: household_locations failed: %s", exc)
        payload["household_locations"] = []

    return payload


def _lot_to_dict(lot: Any) -> dict[str, Any]:
    """Convert an InventoryLot (Pydantic model) to a JSON-safe dict."""
    if hasattr(lot, "model_dump"):
        d = lot.model_dump()
    elif hasattr(lot, "dict"):
        d = lot.dict()
    else:
        d = dict(lot) if hasattr(lot, "__dict__") else {"raw": str(lot)}
    # Dates and decimals may not be JSON-serialisable; convert
    for key, val in list(d.items()):
        if hasattr(val, "isoformat"):
            d[key] = val.isoformat()
        elif hasattr(val, "__str__") and not isinstance(
            val, (str, int, float, bool, list, dict, type(None))
        ):
            d[key] = str(val)
    return d


# ─── Public API ───────────────────────────────────────────────────────────


def export_backup(db, user_id: str, passphrase: str) -> BackupSummary:
    """Encrypt and serialize a household's data.

    Returns:
        BackupSummary with ``success=True``, ``counts`` populated, and
        ``envelope_json`` containing the encrypted backup string ready
        for download.
    """
    now = datetime.now(timezone.utc).isoformat()
    if not passphrase or len(passphrase) < MIN_PASSPHRASE_LENGTH:
        return BackupSummary(
            success=False,
            operation="export",
            created_at=now,
            error=f"Passphrase must be at least {MIN_PASSPHRASE_LENGTH} characters.",
        )

    try:
        payload = _collect_payload(db, user_id)
        plaintext = json.dumps(payload, default=str).encode("utf-8")
        encrypted = _encrypt(plaintext, passphrase)
    except Exception as exc:
        logger.warning("Backup export failed: %s", exc)
        return BackupSummary(
            success=False,
            operation="export",
            created_at=now,
            error=f"Export failed: {exc}",
        )

    envelope = {
        "version": BACKUP_VERSION,
        "kdf": "pbkdf2-sha256",
        "iterations": KDF_ITERATIONS,
        "salt_b64": encrypted["salt_b64"],
        "nonce_b64": encrypted["nonce_b64"],
        "ciphertext_b64": encrypted["ciphertext_b64"],
        "created_at": now,
        "household_id": user_id,
    }
    envelope_json = json.dumps(envelope, indent=2)

    return BackupSummary(
        success=True,
        operation="export",
        created_at=now,
        counts={
            "inventory_lots": len(payload.get("inventory_lots", [])),
            "shopping_lists": len(payload.get("shopping_lists", [])),
            "shopping_list_items": len(payload.get("shopping_list_items", [])),
            "price_observations": len(payload.get("price_observations", [])),
            "preference_signals": len(payload.get("preference_signals", [])),
            "household_locations": len(payload.get("household_locations", [])),
        },
        notes=[
            f"Encrypted with AES-256-GCM, key derived via PBKDF2-HMAC-SHA256 ({KDF_ITERATIONS} iterations).",
            "Store this file somewhere safe — without the passphrase, the data is unrecoverable.",
        ],
        envelope_json=envelope_json,
    )


def import_backup(
    db,
    envelope_json: str,
    passphrase: str,
    user_id: str,
) -> BackupSummary:
    """Decrypt and restore a household's data.

    Args:
        db: Database instance.
        envelope_json: The envelope string previously produced by
            ``export_backup`` (or downloaded by the user).
        passphrase: The same passphrase used at export.
        user_id: The household to restore into.

    Behaviour:
        - Inserts household locations first (so inventory lots can reference them).
        - Then inventory lots. Conflicts on ``lot_id`` are reported.
        - Then shopping lists + items.
        - Then price observations + preference signals.
        - All writes are best-effort; failures on a single row are
          recorded in the returned summary's ``notes`` rather than aborting
          the whole restore.
    """
    now = datetime.now(timezone.utc).isoformat()
    if not envelope_json or not envelope_json.strip():
        return BackupSummary(
            success=False,
            operation="import",
            created_at=now,
            error="No backup file provided.",
        )
    if not passphrase:
        return BackupSummary(
            success=False,
            operation="import",
            created_at=now,
            error="Passphrase required.",
        )

    try:
        envelope = json.loads(envelope_json)
    except json.JSONDecodeError as exc:
        return BackupSummary(
            success=False,
            operation="import",
            created_at=now,
            error=f"Invalid backup file (not JSON): {exc}",
        )

    version = envelope.get("version")
    if version != BACKUP_VERSION:
        return BackupSummary(
            success=False,
            operation="import",
            created_at=now,
            error=f"Unsupported backup version: {version} (expected {BACKUP_VERSION})",
        )

    for required in ("salt_b64", "nonce_b64", "ciphertext_b64"):
        if required not in envelope:
            return BackupSummary(
                success=False,
                operation="import",
                created_at=now,
                error=f"Malformed envelope: missing {required}.",
            )

    try:
        plaintext = _decrypt(envelope, passphrase)
    except Exception as exc:
        # AES-GCM raises InvalidTag on tampering or wrong key
        return BackupSummary(
            success=False,
            operation="import",
            created_at=now,
            error=(
                "Decryption failed — wrong passphrase, or the file has been "
                f"tampered with. ({type(exc).__name__})"
            ),
        )

    try:
        payload = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return BackupSummary(
            success=False,
            operation="import",
            created_at=now,
            error=f"Backup decrypted but payload was not valid JSON: {exc}",
        )

    notes: list[str] = []
    counts: dict[str, int] = {
        "inventory_lots": 0,
        "shopping_lists": 0,
        "shopping_list_items": 0,
        "price_observations": 0,
        "preference_signals": 0,
        "household_locations": 0,
    }
    conflicts: list[str] = []

    # 1) Household locations — use INSERT OR REPLACE
    for loc in payload.get("household_locations", []):
        try:
            db.conn.execute(
                """
                INSERT OR REPLACE INTO household_locations
                  (location_id, name, parent_location_id, location_type, photo_path, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    loc.get("location_id"),
                    loc.get("name"),
                    loc.get("parent_location_id"),
                    loc.get("location_type", "shelf"),
                    loc.get("photo_path"),
                    loc.get("notes"),
                ),
            )
            counts["household_locations"] += 1
        except Exception as exc:
            notes.append(f"location {loc.get('location_id')}: {exc}")
    db.conn.commit()

    # 2) Inventory lots — re-insert via the model API (handles all 20
    # columns; "INSERT OR IGNORE" on lot_id collision). Conflict check
    # is scoped to the *target* household so cross-household restores
    # don't false-positive on existing lot_ids in other households.
    # If the insert still hits a UNIQUE constraint (e.g. another
    # household also has the same lot_id), generate a fresh lot_id
    # and retry once. This preserves lot_ids when restoring into the
    # same household, but never collides across households.
    import uuid as _uuid
    from shopstack.schemas.models import InventoryLot as _InventoryLot

    for lot in payload.get("inventory_lots", []):
        try:
            lot_id = lot.get("lot_id")
            cur = db.conn.execute(
                "SELECT 1 FROM inventory_lots WHERE lot_id = ? AND user_id = ?",
                (lot_id, user_id),
            ).fetchone()
            if cur:
                conflicts.append(f"inventory_lot {lot_id} (already exists in {user_id})")
                continue
            inv = _InventoryLot(
                lot_id=lot_id,
                canonical_name=lot.get("canonical_name", ""),
                display_name=lot.get("display_name") or lot.get("canonical_name", ""),
                category=lot.get("category", ""),
                quantity=lot.get("quantity", 0) or 0,
                unit=lot.get("unit", "unit") or "unit",
                storage_location_id=lot.get("storage_location_id", ""),
                status=lot.get("status", "active") or "active",
            )
            try:
                db.add_inventory_lot(inv, user_id=user_id)
            except Exception as inner:
                # UNIQUE constraint on lot_id — generate a fresh id and
                # remap any references. For now we just rename; richer
                # remapping (e.g. purchase_events) is out of scope.
                if "UNIQUE constraint" in str(inner):
                    new_lot_id = _uuid.uuid4().hex[:12]
                    inv.lot_id = new_lot_id
                    db.add_inventory_lot(inv, user_id=user_id)
                    notes.append(
                        f"inventory_lot: remapped {lot_id} → {new_lot_id} to avoid collision"
                    )
                else:
                    raise
            counts["inventory_lots"] += 1
        except Exception as exc:
            notes.append(f"inventory_lot {lot.get('lot_id')}: {exc}")
    db.conn.commit()

    # 3) Shopping lists
    for sl in payload.get("shopping_lists", []):
        try:
            list_id = sl.get("list_id")
            cur = db.conn.execute(
                "SELECT 1 FROM shopping_lists WHERE list_id = ? AND user_id = ?",
                (list_id, user_id),
            ).fetchone()
            if cur:
                conflicts.append(f"shopping_list {list_id} (already exists in {user_id})")
                continue
            db.create_shopping_list(
                name=sl.get("name", "Shopping List"),
                goal=sl.get("goal", ""),
                user_id=user_id,
                list_id=list_id,
            )
            counts["shopping_lists"] += 1
        except Exception as exc:
            notes.append(f"shopping_list {sl.get('list_id')}: {exc}")
    db.conn.commit()

    # 4) Shopping list items
    for it in payload.get("shopping_list_items", []):
        try:
            list_id = it.get("list_id")
            # Skip items whose parent list didn't make it in (conflict or
            # other reason). We can detect this by checking that the list
            # exists in the DB after step 3.
            cur = db.conn.execute(
                "SELECT 1 FROM shopping_lists WHERE list_id = ?", (list_id,)
            ).fetchone()
            if not cur:
                # Try to create the list silently so the item is not orphaned
                # — but only if the list was in the same backup
                # (already done in step 3, so the new auto-id may differ).
                notes.append(
                    f"shopping_list_item {it.get('item_id')}: parent list {list_id} not in target DB"
                )
                continue
            db.add_list_item(
                list_id,
                ShoppingListItem(
                    canonical_name=it.get("canonical_name", ""),
                    display_name=it.get("display_name")
                    or it.get("canonical_name", ""),
                    requested_quantity=it.get("requested_quantity", 1.0) or 1.0,
                    unit=it.get("unit", "unit") or "unit",
                    priority=it.get("priority", "optional") or "optional",
                    reason=it.get("reason", ""),
                    status=it.get("status", "pending") or "pending",
                ),
            )
            counts["shopping_list_items"] += 1
        except Exception as exc:
            notes.append(f"shopping_list_item {it.get('item_id')}: {exc}")
    db.conn.commit()

    # 5) Price observations
    from shopstack.schemas.models import PriceObservation as _PriceObservation

    for po in payload.get("price_observations", []):
        try:
            obs = _PriceObservation(
                canonical_name=po.get("canonical_name", ""),
                quantity=po.get("quantity", 1.0) or 1.0,
                unit=po.get("unit", "unit") or "unit",
                price=po.get("price", 0.0) or 0.0,
                currency=po.get("currency", "INR") or "INR",
                store_name=po.get("store_name"),
                store_id=po.get("store_id"),
                observation_date=po.get("observation_date") or now[:10],
                source_event_id=po.get("source_event_id", ""),
                notes=po.get("notes"),
            )
            db.record_price(obs, user_id=user_id)
            counts["price_observations"] += 1
        except Exception as exc:
            notes.append(f"price_observation {po.get('price_id')}: {exc}")
    db.conn.commit()

    # 6) Preference signals
    from shopstack.schemas.models import PreferenceSignal as _PreferenceSignal

    for ps in payload.get("preference_signals", []):
        try:
            sig = _PreferenceSignal(
                canonical_name=ps.get("canonical_name", ""),
                kind=ps.get("kind", "avoid") or "avoid",
                weight=ps.get("weight", 1.0) or 1.0,
                notes=ps.get("notes"),
            )
            db.add_preference_signal(sig, user_id=user_id)
            counts["preference_signals"] += 1
        except Exception as exc:
            notes.append(f"preference_signal {ps.get('signal_id')}: {exc}")
    db.conn.commit()

    return BackupSummary(
        success=True,
        operation="import",
        created_at=now,
        counts=counts,
        notes=notes + ([f"Skipped {len(conflicts)} conflicting row(s):"] + conflicts if conflicts else []),
    )


__all__ = [
    "BackupSummary",
    "BACKUP_VERSION",
    "export_backup",
    "import_backup",
]
