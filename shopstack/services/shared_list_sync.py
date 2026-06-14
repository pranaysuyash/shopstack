"""Shared shopping list sync — file-based multi-device collaboration.

The honest "no backend" version of household-shared shopping lists.
Each device reads and writes a JSON file at a path the user configures
(typical locations: a Dropbox/iCloud/Google Drive folder, a network
share, or even a git repo on a home server).

**Conflict policy: additive merge.** On a "Pull" the sync service:
- Adds items that exist in the shared file but not locally
- Does NOT delete items that exist locally but not in the file
- Does NOT overwrite items that exist in both (local is the source of truth
  for active changes; the shared file is for visibility, not for
  authoritative merging)

This is the right policy for a manual-pull sync. For real-time sync
without conflict resolution, a CRDT or operational-transform layer would
be needed; that's not in scope.

**Security note:** the shared file is plain JSON. Items like
``canonical_name`` and ``display_name`` are user-input. If a malicious
party could write to the file, they could plant items in the local list.
Use a trusted file path (your own Dropbox) and don't share it with
untrusted users.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from shopstack.persistence.database import Database

logger = logging.getLogger(__name__)


SHARED_FILE_VERSION = 1


@dataclass
class SyncResult:
    """Result of a push or pull operation."""

    success: bool
    operation: str  # "push" | "pull"
    file_path: str
    counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "operation": self.operation,
            "file_path": self.file_path,
            "counts": self.counts,
            "notes": self.notes,
            "error": self.error,
        }


def _serialize_active_list(db: Database, user_id: str) -> dict[str, Any]:
    """Serialize the user's active shopping list to a JSON-safe dict."""
    sl = db.get_active_shopping_list(user_id=user_id)
    if sl is None:
        return {
            "list_id": "",
            "name": "",
            "goal": "",
            "items": [],
        }
    items = []
    for it in (sl.items or []):
        items.append({
            "item_id": getattr(it, "item_id", ""),
            "canonical_name": getattr(it, "canonical_name", ""),
            "display_name": getattr(it, "display_name", ""),
            "requested_quantity": float(getattr(it, "requested_quantity", 1.0) or 1.0),
            "unit": getattr(it, "unit", "unit") or "unit",
            "priority": getattr(it, "priority", "optional") or "optional",
            "reason": getattr(it, "reason", "") or "",
            "status": getattr(it, "status", "pending") or "pending",
        })
    return {
        "list_id": sl.list_id,
        "name": getattr(sl, "name", "Shopping List"),
        "goal": getattr(sl, "goal", "") or "",
        "items": items,
    }


def _deserialize_into_db(
    db: Database,
    payload: dict[str, Any],
    user_id: str,
) -> dict[str, int]:
    """Apply a pull payload into the local DB. Additive merge.

    Returns counts: {added, existing, total_in_file}.
    """
    items = payload.get("items", [])
    if not items:
        return {"added": 0, "existing": 0, "total_in_file": 0}

    # Ensure we have a list to merge into. If the local DB has no
    # active list, create one.
    sl = db.get_active_shopping_list(user_id=user_id)
    if sl is None:
        from shopstack.schemas.models import ShoppingListItem
        sl = db.create_shopping_list(
            name=payload.get("name") or "Shopping List (synced)",
            goal=payload.get("goal", ""),
            user_id=user_id,
        )

    # Build a set of existing canonical names to detect "already there"
    existing_canonicals = {
        (getattr(it, "canonical_name", "") or "").strip().lower()
        for it in (sl.items or [])
    }

    added = 0
    existing = 0
    for raw in items:
        cname = (raw.get("canonical_name") or "").strip().lower()
        if not cname:
            continue
        if cname in existing_canonicals:
            existing += 1
            continue
        # New item — append. Pass user_id through so the Phase 11
        # permission check authorizes the writer (active_household_id)
        # against the target household the list belongs to.
        from shopstack.schemas.models import ShoppingListItem
        db.add_list_item(
            sl.list_id,
            ShoppingListItem(
                canonical_name=raw.get("canonical_name", ""),
                display_name=raw.get("display_name")
                or raw.get("canonical_name", ""),
                requested_quantity=raw.get("requested_quantity", 1.0) or 1.0,
                unit=raw.get("unit", "unit") or "unit",
                priority=raw.get("priority", "optional") or "optional",
                reason=raw.get("reason", "") or "",
                status=raw.get("status", "pending") or "pending",
            ),
            user_id=user_id,
        )
        existing_canonicals.add(cname)
        added += 1

    return {"added": added, "existing": existing, "total_in_file": len(items)}


# ─── Public API ───────────────────────────────────────────────────────────


def push_to_file(
    db: Database,
    file_path: str,
    user_id: str,
    *,
    device_label: str = "shopstack",
) -> SyncResult:
    """Serialize the active list and write to ``file_path``.

    The file is a self-describing JSON envelope. Existing files are
    overwritten (push is authoritative for the push-side device). If
    the parent directory doesn't exist, it's created.
    """
    now = datetime.now(timezone.utc).isoformat()
    if not file_path or not file_path.strip():
        return SyncResult(
            success=False,
            operation="push",
            file_path=file_path or "",
            error="File path is required.",
        )

    payload = {
        "version": SHARED_FILE_VERSION,
        "kind": "shopstack_shopping_list",
        "exported_at": now,
        "source": {"device": device_label, "household_id": user_id},
        "list": _serialize_active_list(db, user_id),
    }

    try:
        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, default=str)
    except OSError as exc:
        return SyncResult(
            success=False,
            operation="push",
            file_path=file_path,
            error=f"Could not write file: {exc}",
        )

    sl = payload["list"]
    return SyncResult(
        success=True,
        operation="push",
        file_path=file_path,
        counts={
            "items_pushed": len(sl["items"]),
            "list_count": 1,
        },
        notes=[
            f"Pushed {len(sl['items'])} items at {now}",
            f"Source: {device_label} ({user_id})",
        ],
    )


def pull_from_file(
    db: Database,
    file_path: str,
    user_id: str,
) -> SyncResult:
    """Read ``file_path`` and merge the items into the local active list.

    Additive merge — never deletes local items. See module docstring
    for the conflict policy.
    """
    now = datetime.now(timezone.utc).isoformat()
    if not file_path or not file_path.strip():
        return SyncResult(
            success=False,
            operation="pull",
            file_path=file_path or "",
            error="File path is required.",
        )
    if not os.path.isfile(file_path):
        return SyncResult(
            success=False,
            operation="pull",
            file_path=file_path,
            error=f"File not found: {file_path}",
        )

    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return SyncResult(
            success=False,
            operation="pull",
            file_path=file_path,
            error=f"Could not read or parse file: {exc}",
        )

    if not isinstance(payload, dict) or payload.get("kind") != "shopstack_shopping_list":
        return SyncResult(
            success=False,
            operation="pull",
            file_path=file_path,
            error="File is not a ShopStack shopping-list sync envelope.",
        )

    version = payload.get("version")
    if version != SHARED_FILE_VERSION:
        return SyncResult(
            success=False,
            operation="pull",
            file_path=file_path,
            error=(
                f"Unsupported sync-file version: {version} "
                f"(expected {SHARED_FILE_VERSION})"
            ),
        )

    sl = payload.get("list", {})
    counts = _deserialize_into_db(db, sl, user_id)
    return SyncResult(
        success=True,
        operation="pull",
        file_path=file_path,
        counts=counts,
        notes=[
            f"Pulled at {now} from {payload.get('source', {}).get('device', 'unknown')}",
            f"Source exported at {payload.get('exported_at', 'unknown')}",
            (
                f"Added {counts['added']} new item(s); {counts['existing']} already present locally."
            ),
        ],
    )


__all__ = [
    "SyncResult",
    "SHARED_FILE_VERSION",
    "push_to_file",
    "pull_from_file",
]
