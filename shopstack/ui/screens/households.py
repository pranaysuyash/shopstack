"""Households management UI screen — Phase 10 #1 wiring.

Thin server-rendered panel that lists the active household's
members, lets the active user add/remove/change-role other
members, and surfaces permission errors as toasts.
"""
from __future__ import annotations

import logging
from typing import Any

from shopstack.app_context import current_user_id, db
from shopstack.services.permissions import (
    add_member,
    change_role,
    list_members,
    list_households_for_user,
    render_members_html,
    remove_member,
)

logger = logging.getLogger(__name__)


def households_panel_screen() -> str:
    """Render the household members panel for the active household.

    Returns XSS-safe HTML. Empty-state when there are no
    members to show.
    """
    try:
        user_id = current_user_id() or ""
        # Active household is read from app config
        active = db.get_config_value("active_household_id", "") or ""
        if not active:
            return (
                "<div class='perm-empty'>"
                "No active household. Use the household dropdown to switch."
                "</div>"
            )
        members = list_members(active, db)
        return render_members_html(members)
    except Exception as exc:
        logger.debug("households_panel_screen failed: %s", exc)
        return ""


def add_member_screen(household_id: str, user_id: str, role: str, actor_id: str) -> str:
    """Add a member, returning the updated members HTML + a toast."""
    try:
        result = add_member(household_id, user_id, role, actor_id, db)
        members_html = list_members(household_id, db)
        if result.get("added"):
            return (
                members_html,
                f"✅ Added {user_id} as {role}.",
            )
        return members_html, f"❌ {result.get('reason', 'Failed')}."
    except Exception as exc:
        logger.debug("add_member_screen failed: %s", exc)
        return list_members(household_id, db), f"❌ Error: {exc}"


def remove_member_screen(household_id: str, user_id: str, actor_id: str) -> str:
    """Remove a member, returning the updated members HTML + a toast."""
    try:
        result = remove_member(household_id, user_id, actor_id, db)
        members_html = list_members(household_id, db)
        if result.get("removed"):
            return members_html, f"✅ Removed {user_id}."
        return members_html, f"❌ {result.get('reason', 'Failed')}."
    except Exception as exc:
        logger.debug("remove_member_screen failed: %s", exc)
        return list_members(household_id, db), f"❌ Error: {exc}"


def change_role_screen(household_id: str, user_id: str, new_role: str, actor_id: str) -> str:
    """Change a member's role, returning the updated HTML + toast."""
    try:
        result = change_role(household_id, user_id, new_role, actor_id, db)
        members_html = list_members(household_id, db)
        if result.get("changed"):
            return members_html, f"✅ {user_id} is now {new_role}."
        return members_html, f"❌ {result.get('reason', 'Failed')}."
    except Exception as exc:
        logger.debug("change_role_screen failed: %s", exc)
        return list_members(household_id, db), f"❌ Error: {exc}"


def list_user_households_screen() -> str:
    """Render a small 'your households' summary line."""
    try:
        user_id = current_user_id() or ""
        rows = list_households_for_user(user_id, db)
        if not rows:
            return "<div class='perm-empty'>You're not a member of any household yet.</div>"
        chips = "".join(
            "<span class='perm-hh-chip'>"
            + escape(str(r.get("name", r.get("household_id", "")))
            + " · "
            + escape(str(r.get("role", ""))))
            + "</span>"
            for r in rows
        )
        return f"<div class='perm-hh-chips'>{chips}</div>"
    except Exception as exc:
        logger.debug("list_user_households_screen failed: %s", exc)
        return ""


__all__ = [
    "add_member_screen",
    "change_role_screen",
    "households_panel_screen",
    "list_user_households_screen",
    "remove_member_screen",
]
