"""Household permissioning — Phase 10 #1 (the complete solution).

**1st-principles design:**

ShopStack data is household-scoped. Every read and write
on an inventory lot, a shopping list, a price observation,
or a trace should be authorized against a *membership* in
the household, not against a raw ``user_id`` string.

Roles:

- **owner** — full control. Can manage members, change
  roles, and remove the household.
- **member** — read + write. Can add inventory, consume,
  observe prices, log traces. Cannot manage members.
- **guest** — read-only. Can browse the household's data
  but cannot mutate.

**One owner per household.** Removing the last owner is
refused (would orphan the household). Demoting the last
owner to a non-owner role is also refused.

**Why a separate module:**

Permissioning is a cross-cutting concern. Centralizing it in
``shopstack.services.permissions`` means:
- Every write path imports the same ``can_write()`` check.
- Tests are isolated from the DB schema.
- Adding a new role or a new action is a single-file change.

**Failure modes:**

- Caller is not a member → ``can_*`` returns ``False``.
  Callers must surface a permission-denied error to the
  user (or HTTP 403 for the SMS webhook).
- Database unreachable → ``can_*`` returns ``False`` (fail
  closed). Permission checks never silently allow on
  failure.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from html import escape
from typing import Any

logger = logging.getLogger(__name__)


# ─── Role constants ──────────────────────────────────────────────


OWNER = "owner"
MEMBER = "member"
GUEST = "guest"

VALID_ROLES: tuple[str, ...] = (OWNER, MEMBER, GUEST)


# ─── Result dataclass ────────────────────────────────────────────


@dataclass
class PermissionDecision:
    """Structured answer to a permission check.

    Carries the decision (allowed / denied) and the reason
    so the caller can surface a meaningful error.
    """

    allowed: bool
    reason: str
    role: str = ""  # the caller's role, if any

    def __bool__(self) -> bool:
        return self.allowed


# ─── Helpers ────────────────────────────────────────────────────


def _role_rank(role: str) -> int:
    """Numeric rank for role ordering. Higher = more privilege."""
    return {OWNER: 3, MEMBER: 2, GUEST: 1}.get(role, 0)


def _normalize_user_id(user_id: str | None) -> str:
    return (user_id or "").strip()


# ─── Core permission checks ──────────────────────────────────────


def can_read(user_id: str, household_id: str, db: Any) -> PermissionDecision:
    """True if ``user_id`` is a member of ``household_id``.

    Reads are allowed for *any* role (owner, member, guest).
    Empty ``user_id`` is denied (defensive).
    """
    uid = _normalize_user_id(user_id)
    hid = (household_id or "").strip()
    if not uid or not hid:
        return PermissionDecision(allowed=False, reason="empty user_id or household_id")
    try:
        member = db.get_household_member(hid, uid)
    except Exception as exc:
        logger.debug("can_read DB error: %s", exc)
        return PermissionDecision(allowed=False, reason=f"db error: {exc}")
    if member is None:
        return PermissionDecision(
            allowed=False, reason=f"user {uid!r} is not a member of {hid!r}"
        )
    return PermissionDecision(allowed=True, reason="member", role=str(member.get("role", "")))


def can_write(user_id: str, household_id: str, db: Any) -> PermissionDecision:
    """True if ``user_id`` can mutate ``household_id``'s data.

    Writes are allowed for owners and members. Guests are
    denied. Empty inputs are denied.
    """
    decision = can_read(user_id, household_id, db)
    if not decision.allowed:
        return decision
    if _role_rank(decision.role) < _role_rank(MEMBER):
        return PermissionDecision(
            allowed=False,
            reason=f"role {decision.role!r} is read-only",
            role=decision.role,
        )
    return PermissionDecision(
        allowed=True, reason=f"role {decision.role!r} can write", role=decision.role
    )


def can_admin(user_id: str, household_id: str, db: Any) -> PermissionDecision:
    """True if ``user_id`` can manage members / change roles.

    Only owners. Members and guests are denied.
    """
    decision = can_read(user_id, household_id, db)
    if not decision.allowed:
        return decision
    if _role_rank(decision.role) < _role_rank(OWNER):
        return PermissionDecision(
            allowed=False,
            reason=f"role {decision.role!r} cannot administer",
            role=decision.role,
        )
    return PermissionDecision(
        allowed=True, reason=f"role {decision.role!r} can admin", role=decision.role
    )


def require_read(user_id: str, household_id: str, db: Any) -> None:
    """Raise ``PermissionError`` if ``user_id`` cannot read."""
    decision = can_read(user_id, household_id, db)
    if not decision.allowed:
        raise PermissionError(decision.reason)


def require_write(user_id: str, household_id: str, db: Any) -> None:
    """Raise ``PermissionError`` if ``user_id`` cannot write."""
    decision = can_write(user_id, household_id, db)
    if not decision.allowed:
        raise PermissionError(decision.reason)


def require_admin(user_id: str, household_id: str, db: Any) -> None:
    """Raise ``PermissionError`` if ``user_id`` cannot admin."""
    decision = can_admin(user_id, household_id, db)
    if not decision.allowed:
        raise PermissionError(decision.reason)


# ─── Convenience: list + add + remove + change role ────────────


def list_members(household_id: str, db: Any) -> list[dict[str, str]]:
    """List members of a household (oldest first)."""
    try:
        return list(db.list_household_members(household_id) or [])
    except Exception as exc:
        logger.debug("list_members error: %s", exc)
        return []


def list_households_for_user(user_id: str, db: Any) -> list[dict[str, str]]:
    """List households a user is in (with their role)."""
    try:
        return list(db.list_households_for_user(user_id) or [])
    except Exception as exc:
        logger.debug("list_households_for_user error: %s", exc)
        return []


def add_member(
    household_id: str,
    user_id: str,
    role: str,
    actor_id: str,
    db: Any,
) -> dict[str, Any]:
    """Add ``user_id`` to ``household_id`` with the given role.

    Requires ``actor_id`` to have admin permission. Returns
    ``{"added": bool, "reason": str, "role": str}``.
    """
    admin_check = can_admin(actor_id, household_id, db)
    if not admin_check.allowed:
        return {"added": False, "reason": admin_check.reason, "role": ""}
    if role not in VALID_ROLES:
        return {"added": False, "reason": f"invalid role {role!r}", "role": ""}
    ok = db.add_household_member(household_id, user_id, role=role)
    if not ok:
        return {"added": False, "reason": "user already a member or household missing", "role": ""}
    return {"added": True, "reason": "added", "role": role}


def remove_member(
    household_id: str,
    user_id: str,
    actor_id: str,
    db: Any,
) -> dict[str, Any]:
    """Remove ``user_id`` from ``household_id``.

    Requires ``actor_id`` to have admin permission. Refused
    if removing the last owner. Users can also remove
    themselves (without admin).
    """
    is_self = _normalize_user_id(actor_id) == _normalize_user_id(user_id)
    if not is_self:
        admin_check = can_admin(actor_id, household_id, db)
        if not admin_check.allowed:
            return {"removed": False, "reason": admin_check.reason}
    ok = db.remove_household_member(household_id, user_id)
    if not ok:
        return {"removed": False, "reason": "not a member, or last owner (can't orphan)"}
    return {"removed": True, "reason": "removed"}


def change_role(
    household_id: str,
    user_id: str,
    new_role: str,
    actor_id: str,
    db: Any,
) -> dict[str, Any]:
    """Change ``user_id``'s role in ``household_id``.

    Requires ``actor_id`` to have admin permission. Refused
    if the change would demote the last owner.
    """
    admin_check = can_admin(actor_id, household_id, db)
    if not admin_check.allowed:
        return {"changed": False, "reason": admin_check.reason}
    if new_role not in VALID_ROLES:
        return {"changed": False, "reason": f"invalid role {new_role!r}"}
    ok = db.update_household_member_role(household_id, user_id, new_role)
    if not ok:
        return {"changed": False, "reason": "user not a member, or last owner (can't demote)"}
    return {"changed": True, "reason": "role updated", "role": new_role}


# ─── HTML rendering ────────────────────────────────────────────


def _role_badge(role: str) -> str:
    # Each role has a bg color and a text color that pass WCAG AA in both
    # light and dark mode. We previously used `color:#fff` on every bg
    # (which fails for the muted/grey roles) — switch to per-role text
    # colors that always contrast with their bg.
    bg_color, text_color = {
        OWNER:  ("var(--accent, #176B49)",         "#fff"),
        MEMBER: ("var(--bg-warm, #FFF1D6)",         "var(--text, #1F1812)"),
        GUEST:  ("var(--bg-input, #FFF7EA)",        "var(--text-muted, #5F5144)"),
    }.get(role, ("var(--bg-input, #FFF7EA)", "var(--text-muted, #5F5144)"))
    return (
        f"<span class='perm-role-badge' style='background:{bg_color};color:{text_color};'>{escape(role.title())}</span>"
    )


def render_members_html(members: list[dict[str, str]]) -> str:
    """Render the household members list as XSS-safe HTML."""
    if not members:
        return (
            "<div class='perm-empty'>"
            "👤 No members yet. Add yourself + family below."
            "</div>"
        )
    rows: list[str] = []
    for m in members:
        uid = str(m.get("user_id", ""))
        role = str(m.get("role", ""))
        joined = str(m.get("joined_at", ""))
        # Truncate the joined_at to YYYY-MM-DD for compactness
        joined_short = joined[:10] if len(joined) >= 10 else joined
        rows.append(
            "<div class='perm-member-row'>"
            f"<div class='perm-member-name'>{escape(uid)}</div><div class='perm-member-role'>{_role_badge(role)}</div>"
            f"<div class='perm-member-joined'>since {escape(joined_short)}</div>"
            "</div>"
        )
    return "".join(rows)


__all__ = [
    "GUEST",
    "MEMBER",
    "OWNER",
    "PermissionDecision",
    "VALID_ROLES",
    "add_member",
    "can_admin",
    "can_read",
    "can_write",
    "change_role",
    "list_households_for_user",
    "list_members",
    "render_members_html",
    "remove_member",
    "require_admin",
    "require_read",
    "require_write",
]
