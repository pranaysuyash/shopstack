"""Tests for shopstack.services.permissions (Phase 10 #1)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from shopstack.services.permissions import (
    GUEST,
    MEMBER,
    OWNER,
    VALID_ROLES,
    PermissionDecision,
    add_member,
    can_admin,
    can_read,
    can_write,
    change_role,
    list_households_for_user,
    list_members,
    remove_member,
    render_members_html,
    require_admin,
    require_read,
    require_write,
)


class FakeDB:
    """Minimal DB stub for permission tests."""

    def __init__(self, members: dict[tuple[str, str], dict] | None = None,
                 households: dict[str, dict] | None = None):
        # members is keyed by (household_id, user_id)
        self.members = members or {}
        self.households = households or {
            "hh-1": {"household_id": "hh-1", "name": "Test Home"},
            "hh-2": {"household_id": "hh-2", "name": "Beach House"},
        }

    def get_household_member(self, household_id: str, user_id: str):
        return self.members.get((household_id, user_id))

    def add_household_member(self, household_id: str, user_id: str, role: str = "member"):
        if (household_id, user_id) in self.members:
            return False
        if household_id not in self.households:
            return False
        self.members[(household_id, user_id)] = {
            "household_id": household_id,
            "user_id": user_id,
            "role": role,
            "joined_at": datetime.now().isoformat(),
        }
        return True

    def remove_household_member(self, household_id: str, user_id: str):
        if (household_id, user_id) not in self.members:
            return False
        if self._is_last_owner(household_id, user_id):
            return False
        del self.members[(household_id, user_id)]
        return True

    def update_household_member_role(self, household_id: str, user_id: str, new_role: str):
        if (household_id, user_id) not in self.members:
            return False
        if new_role != "owner" and self._is_last_owner(household_id, user_id):
            return False
        self.members[(household_id, user_id)]["role"] = new_role
        return True

    def list_household_members(self, household_id: str):
        return [m for (h, _), m in self.members.items() if h == household_id]

    def list_households_for_user(self, user_id: str):
        return [
            {**self.households[h], "role": m["role"], "joined_at": m["joined_at"]}
            for (h, u), m in self.members.items()
            if u == user_id and h in self.households
        ]

    def _is_last_owner(self, household_id: str, user_id: str) -> bool:
        member = self.get_household_member(household_id, user_id)
        if not member or member.get("role") != "owner":
            return False
        owners = [u for (h, u), m in self.members.items() if h == household_id and m.get("role") == "owner"]
        return len(owners) == 1 and owners[0] == user_id


# ── Constants ────────────────────────────────────────────────────


def test_valid_roles_set():
    assert "owner" in VALID_ROLES
    assert "member" in VALID_ROLES
    assert "guest" in VALID_ROLES
    assert len(VALID_ROLES) == 3


# ── can_read ─────────────────────────────────────────────────────


def test_can_read_member_allowed():
    db = FakeDB({("hh-1", "alice"): {"user_id": "alice", "role": "member"}})
    assert can_read("alice", "hh-1", db).allowed is True


def test_can_read_owner_allowed():
    db = FakeDB({("hh-1", "alice"): {"user_id": "alice", "role": "owner"}})
    assert can_read("alice", "hh-1", db).allowed is True


def test_can_read_guest_allowed():
    db = FakeDB({("hh-1", "guest1"): {"user_id": "guest1", "role": "guest"}})
    assert can_read("guest1", "hh-1", db).allowed is True


def test_can_read_non_member_denied():
    db = FakeDB()
    decision = can_read("bob", "hh-1", db)
    assert decision.allowed is False
    assert "not a member" in decision.reason


def test_can_read_empty_inputs_denied():
    db = FakeDB()
    assert can_read("", "hh-1", db).allowed is False
    assert can_read("alice", "", db).allowed is False


def test_can_read_db_error_denied():
    class _BadDB:
        def get_household_member(self, *a, **kw):
            raise RuntimeError("db down")
    decision = can_read("alice", "hh-1", _BadDB())
    assert decision.allowed is False
    assert "db error" in decision.reason


# ── can_write ────────────────────────────────────────────────────


def test_can_write_owner_allowed():
    db = FakeDB({("hh-1", "alice"): {"user_id": "alice", "role": "owner"}})
    assert can_write("alice", "hh-1", db).allowed is True


def test_can_write_member_allowed():
    db = FakeDB({("hh-1", "alice"): {"user_id": "alice", "role": "member"}})
    assert can_write("alice", "hh-1", db).allowed is True


def test_can_write_guest_denied():
    db = FakeDB({("hh-1", "guest1"): {"user_id": "guest1", "role": "guest"}})
    decision = can_write("guest1", "hh-1", db)
    assert decision.allowed is False
    assert "read-only" in decision.reason


def test_can_write_non_member_denied():
    db = FakeDB()
    assert can_write("bob", "hh-1", db).allowed is False


# ─- can_admin ───────────────────────────────────────────────────


def test_can_admin_owner_allowed():
    db = FakeDB({("hh-1", "alice"): {"user_id": "alice", "role": "owner"}})
    assert can_admin("alice", "hh-1", db).allowed is True


def test_can_admin_member_denied():
    db = FakeDB({("hh-1", "alice"): {"user_id": "alice", "role": "member"}})
    decision = can_admin("alice", "hh-1", db)
    assert decision.allowed is False
    assert "cannot administer" in decision.reason


def test_can_admin_guest_denied():
    db = FakeDB({("hh-1", "guest1"): {"user_id": "guest1", "role": "guest"}})
    assert can_admin("guest1", "hh-1", db).allowed is False


# ─- require_* helpers ─────────────────────────────────────────


def test_require_read_passes():
    db = FakeDB({("hh-1", "alice"): {"user_id": "alice", "role": "member"}})
    require_read("alice", "hh-1", db)  # should not raise


def test_require_read_raises():
    db = FakeDB()
    with pytest.raises(PermissionError):
        require_read("bob", "hh-1", db)


def test_require_write_passes():
    db = FakeDB({("hh-1", "alice"): {"user_id": "alice", "role": "member"}})
    require_write("alice", "hh-1", db)


def test_require_write_raises_for_guest():
    db = FakeDB({("hh-1", "guest1"): {"user_id": "guest1", "role": "guest"}})
    with pytest.raises(PermissionError):
        require_write("guest1", "hh-1", db)


def test_require_admin_passes():
    db = FakeDB({("hh-1", "alice"): {"user_id": "alice", "role": "owner"}})
    require_admin("alice", "hh-1", db)


def test_require_admin_raises_for_member():
    db = FakeDB({("hh-1", "alice"): {"user_id": "alice", "role": "member"}})
    with pytest.raises(PermissionError):
        require_admin("alice", "hh-1", db)


# ─- list_members / list_households_for_user ──────────────────


def test_list_members_returns_all_members():
    db = FakeDB({
        ("hh-1", "alice"): {"user_id": "alice", "role": "owner", "joined_at": "2026-01-01"},
        ("hh-1", "bob"): {"user_id": "bob", "role": "member", "joined_at": "2026-01-02"},
    })
    members = list_members("hh-1", db)
    assert len(members) == 2


def test_list_members_empty_household():
    db = FakeDB()
    assert list_members("hh-1", db) == []


def test_list_households_for_user():
    db = FakeDB({
        ("hh-1", "alice"): {"user_id": "alice", "role": "owner", "joined_at": "2026-01-01"},
        ("hh-2", "alice"): {"user_id": "alice", "role": "guest", "joined_at": "2026-02-01"},
    })
    rows = list_households_for_user("alice", db)
    assert len(rows) == 2
    # Roles should be preserved
    roles = {r.get("role") for r in rows}
    assert "owner" in roles
    assert "guest" in roles


# ─- add_member / remove_member / change_role ──────────────────


def test_add_member_as_owner():
    db = FakeDB({("hh-1", "alice"): {"user_id": "alice", "role": "owner"}})
    result = add_member("hh-1", "bob", "member", "alice", db)
    assert result["added"] is True
    assert (("hh-1", "bob") in db.members)


def test_add_member_as_member_denied():
    db = FakeDB({("hh-1", "alice"): {"user_id": "alice", "role": "member"}})
    result = add_member("hh-1", "bob", "member", "alice", db)
    assert result["added"] is False
    assert "cannot administer" in result["reason"]


def test_add_member_invalid_role():
    db = FakeDB({("hh-1", "alice"): {"user_id": "alice", "role": "owner"}})
    result = add_member("hh-1", "bob", "superadmin", "alice", db)
    assert result["added"] is False
    assert "invalid role" in result["reason"]


def test_remove_member_as_owner():
    db = FakeDB({
        ("hh-1", "alice"): {"user_id": "alice", "role": "owner"},
        ("hh-1", "bob"): {"user_id": "bob", "role": "member"},
    })
    result = remove_member("hh-1", "bob", "alice", db)
    assert result["removed"] is True
    assert (("hh-1", "bob") not in db.members)


def test_remove_member_as_member_denied():
    db = FakeDB({
        ("hh-1", "alice"): {"user_id": "alice", "role": "member"},
        ("hh-1", "bob"): {"user_id": "bob", "role": "member"},
    })
    result = remove_member("hh-1", "bob", "alice", db)
    assert result["removed"] is False


def test_remove_member_self_allowed_for_any_role():
    db = FakeDB({("hh-1", "alice"): {"user_id": "alice", "role": "member"}})
    result = remove_member("hh-1", "alice", "alice", db)
    assert result["removed"] is True


def test_remove_last_owner_refused():
    db = FakeDB({("hh-1", "alice"): {"user_id": "alice", "role": "owner"}})
    result = remove_member("hh-1", "alice", "alice", db)
    assert result["removed"] is False
    assert "last owner" in result["reason"]


def test_change_role_as_owner():
    db = FakeDB({
        ("hh-1", "alice"): {"user_id": "alice", "role": "owner"},
        ("hh-1", "bob"): {"user_id": "bob", "role": "member"},
    })
    result = change_role("hh-1", "bob", "guest", "alice", db)
    assert result["changed"] is True
    assert db.members[("hh-1", "bob")]["role"] == "guest"


def test_change_role_demote_last_owner_refused():
    db = FakeDB({("hh-1", "alice"): {"user_id": "alice", "role": "owner"}})
    result = change_role("hh-1", "alice", "member", "alice", db)
    assert result["changed"] is False
    assert "last owner" in result["reason"]


def test_change_role_as_member_denied():
    db = FakeDB({
        ("hh-1", "alice"): {"user_id": "alice", "role": "member"},
        ("hh-1", "bob"): {"user_id": "bob", "role": "member"},
    })
    result = change_role("hh-1", "bob", "guest", "alice", db)
    assert result["changed"] is False


def test_change_role_with_two_owners_can_demote_one():
    db = FakeDB({
        ("hh-1", "alice"): {"user_id": "alice", "role": "owner"},
        ("hh-1", "bob"): {"user_id": "bob", "role": "owner"},
    })
    # Alice is an owner; she can demote Bob to member
    result = change_role("hh-1", "bob", "member", "alice", db)
    assert result["changed"] is True


# ─- HTML rendering ────────────────────────────────────────────


def test_render_members_empty():
    html = render_members_html([])
    assert "No members" in html or "perm-empty" in html


def test_render_members_basic():
    members = [
        {"user_id": "alice", "role": "owner", "joined_at": "2026-01-01T10:00:00"},
        {"user_id": "bob", "role": "member", "joined_at": "2026-01-02T10:00:00"},
    ]
    html = render_members_html(members)
    assert "alice" in html
    assert "bob" in html
    assert "owner" in html.lower()
    assert "member" in html.lower()
    # Joined date is truncated to YYYY-MM-DD
    assert "2026-01-01" in html
    assert "2026-01-02" in html


def test_render_members_escapes_xss():
    members = [
        {"user_id": "<script>alert(1)</script>", "role": "member", "joined_at": "2026-01-01"},
    ]
    html = render_members_html(members)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_render_members_role_badge():
    members = [
        {"user_id": "alice", "role": "owner", "joined_at": "2026-01-01"},
    ]
    html = render_members_html(members)
    # The owner badge has the green accent color
    assert "176B49" in html or "perm-role-badge" in html


# ─- PermissionDecision bool semantics ─────────────────────────


def test_permission_decision_bool():
    d_allowed = PermissionDecision(allowed=True, reason="ok")
    d_denied = PermissionDecision(allowed=False, reason="nope")
    assert bool(d_allowed) is True
    assert bool(d_denied) is False
    # Used in `if can_write(...)` patterns
    assert d_allowed  # truthy
    assert not d_denied  # falsy


# ─- Backward compatibility: no role on row ────────────────────


def test_can_read_with_no_role_field():
    """If a member row is missing the role field, treat as guest (denied writes)."""
    db = FakeDB({("hh-1", "alice"): {"user_id": "alice"}})  # no role
    assert can_read("alice", "hh-1", db).allowed is True
    # No role → 0 rank → write denied
    assert can_write("alice", "hh-1", db).allowed is False
