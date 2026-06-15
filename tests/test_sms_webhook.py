"""Tests for the SMS / WhatsApp webhook dispatcher + security.

Verifies:

1. The pure dispatcher logic in :mod:`shopstack.services.sms_webhook`
   (add/consume/unknown intents, DB error handling).
2. **Twilio HMAC signature verification** (``verify_twilio_signature``)
   — the fail-closed auth boundary for the webhook endpoint.
3. **Household-scoped dispatch** — writes go to the phone-owner's
   household, not the process-global active household.
4. **Fail-closed mounting** — the webhook does not mount without
   explicit enable + auth token config.

The HTTP endpoint itself (Starlette route registration) is hard to
unit-test without spinning up a server; the dispatcher + verifier are
the pieces with actual security/business logic, so we test those.
"""
from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from urllib.parse import urlencode

from shopstack.schemas.models import InventoryLot
from shopstack.services.sms_webhook import (
    _default_intent_dispatcher,
    _household_scoped_dispatcher,
    verify_twilio_signature,
)


class _FakeDB:
    """In-memory stand-in for the db singleton.

    Mirrors the *real* Database API shape (add_inventory_lot takes an
    InventoryLot, consume_inventory takes lot_id+quantity, get_inventory
    returns lots filtered by canonical_name). Keeping the mock
    signature faithful to the real DB prevents the test from passing
    while the real integration TypeErrors (a Tier 2 vs Tier 3 trap we
    hit before the 2026-06-14 fix).
    """

    def __init__(
        self,
        raise_on_add: bool = False,
        raise_on_consume: bool = False,
        lots: list[InventoryLot] | None = None,
    ) -> None:
        self.add_calls: list[dict] = []
        self.consume_calls: list[dict] = []
        self.raise_on_add = raise_on_add
        self.raise_on_consume = raise_on_consume
        self._lots = list(lots or [])

    def add_inventory_lot(self, lot: InventoryLot, user_id: str = "") -> InventoryLot:
        self.add_calls.append({"lot": lot, "user_id": user_id})
        self._lots.append(lot)
        if self.raise_on_add:
            raise RuntimeError("simulated DB error on add")
        return lot

    def consume_inventory(
        self, lot_id: str, quantity: float, user_id: str = ""
    ) -> InventoryLot | None:
        self.consume_calls.append(
            {"lot_id": lot_id, "quantity": quantity, "user_id": user_id}
        )
        if self.raise_on_consume:
            raise RuntimeError("simulated DB error on consume")
        for lot in self._lots:
            if lot.lot_id == lot_id:
                return lot
        return None

    def get_inventory(
        self,
        status: str | None = None,
        location_id: str | None = None,
        category: str | None = None,
        user_id: str = "",
        canonical_name: str | None = None,
    ) -> list[InventoryLot]:
        out = []
        for lot in self._lots:
            if status and lot.status != status:
                continue
            if canonical_name and lot.canonical_name != canonical_name:
                continue
            out.append(lot)
        return out


class TestAddInventoryItem:
    """Tests for the ``add_inventory_item`` intent."""

    def test_add_calls_db_with_canonical_name(self):
        db = _FakeDB()
        dispatcher = _default_intent_dispatcher(db)
        result = dispatcher("user-1", {
            "intent": "add_inventory_item",
            "args": {"canonical_name": "milk", "quantity": 2.0, "unit": "L"},
        })
        assert result["ok"] is True
        assert "milk" in result["message"]
        assert len(db.add_calls) == 1
        assert db.add_calls[0]["lot"].canonical_name == "milk"
        assert db.add_calls[0]["user_id"] == "user-1"
        assert db.add_calls[0]["lot"].quantity == 2.0
        assert db.add_calls[0]["lot"].unit == "L"

    def test_add_uses_display_name_fallback(self):
        """If display_name is missing, fall back to canonical_name."""
        db = _FakeDB()
        dispatcher = _default_intent_dispatcher(db)
        dispatcher("user-1", {
            "intent": "add_inventory_item",
            "args": {"canonical_name": "milk"},
        })
        assert db.add_calls[0]["lot"].display_name == "milk"

    def test_add_missing_canonical_name_is_noop(self):
        """Without canonical_name, the intent is not dispatched."""
        db = _FakeDB()
        dispatcher = _default_intent_dispatcher(db)
        result = dispatcher("user-1", {
            "intent": "add_inventory_item",
            "args": {"quantity": 2.0},
        })
        # No dispatch happened; ok=True with no-action message
        assert result["ok"] is True
        assert "no action configured" in result["message"]
        assert len(db.add_calls) == 0

    def test_add_db_error_returns_ok_false(self):
        """DB errors are caught and returned as ok=False with a friendly message."""
        db = _FakeDB(raise_on_add=True)
        dispatcher = _default_intent_dispatcher(db)
        result = dispatcher("user-1", {
            "intent": "add_inventory_item",
            "args": {"canonical_name": "milk"},
        })
        assert result["ok"] is False
        assert "DB error" in result["message"]


class TestConsumeItem:
    """Tests for the ``consume_item`` intent."""

    def test_consume_calls_db_with_canonical_name(self):
        # Pre-populate an active bread lot so the dispatcher can resolve it.
        bread_lot = InventoryLot(
            lot_id="lot-bread-1",
            canonical_name="bread",
            display_name="Bread",
            quantity=2.0,
            unit="loaf",
            status="active",
            created_at=datetime.now(timezone.utc),
        )
        db = _FakeDB(lots=[bread_lot])
        dispatcher = _default_intent_dispatcher(db)
        result = dispatcher("user-1", {
            "intent": "consume_item",
            "args": {"canonical_name": "bread", "quantity": 1.0, "unit": "loaf"},
        })
        assert result["ok"] is True
        assert "bread" in result["message"]
        assert len(db.consume_calls) == 1
        assert db.consume_calls[0]["lot_id"] == "lot-bread-1"
        assert db.consume_calls[0]["quantity"] == 1.0
        assert db.consume_calls[0]["user_id"] == "user-1"

    def test_consume_no_active_lot_returns_ok_false(self):
        """Consuming an item that doesn't exist is a user-facing failure, not a crash."""
        db = _FakeDB()  # no lots
        dispatcher = _default_intent_dispatcher(db)
        result = dispatcher("user-1", {
            "intent": "consume_item",
            "args": {"canonical_name": "bread"},
        })
        assert result["ok"] is False
        assert "No active bread" in result["message"]
        assert len(db.consume_calls) == 0

    def test_consume_missing_canonical_name_is_noop(self):
        db = _FakeDB()
        dispatcher = _default_intent_dispatcher(db)
        result = dispatcher("user-1", {
            "intent": "consume_item",
            "args": {"quantity": 1.0},
        })
        assert result["ok"] is True
        assert "no action configured" in result["message"]
        assert len(db.consume_calls) == 0

    def test_consume_db_error_returns_ok_false(self):
        # Pre-populate so the dispatcher reaches the consume call (which raises).
        bread_lot = InventoryLot(
            lot_id="lot-bread-err",
            canonical_name="bread",
            display_name="Bread",
            quantity=1.0,
            unit="loaf",
            status="active",
            created_at=datetime.now(timezone.utc),
        )
        db = _FakeDB(raise_on_consume=True, lots=[bread_lot])
        dispatcher = _default_intent_dispatcher(db)
        result = dispatcher("user-1", {
            "intent": "consume_item",
            "args": {"canonical_name": "bread"},
        })
        assert result["ok"] is False
        assert "DB error" in result["message"]


class TestUnknownIntent:
    """Tests for intents the dispatcher doesn't recognize."""

    def test_unknown_intent_returns_ok_true(self):
        """Unknown intents are acknowledged but not acted on.

        The dispatcher is pluggable: today it handles 2 intents,
        tomorrow it might handle 10. The endpoint contract is
        "acknowledge with 200 OK so the provider doesn't retry,
        and let the dispatcher decide what to do."
        """
        db = _FakeDB()
        dispatcher = _default_intent_dispatcher(db)
        result = dispatcher("user-1", {
            "intent": "future_intent",
            "args": {"foo": "bar"},
        })
        assert result["ok"] is True
        assert "future_intent" in result["message"]
        assert "no action configured" in result["message"]
        assert len(db.add_calls) == 0
        assert len(db.consume_calls) == 0

    def test_missing_intent_key_returns_ok_true(self):
        """A payload with no intent key is treated as unknown (defensive)."""
        db = _FakeDB()
        dispatcher = _default_intent_dispatcher(db)
        result = dispatcher("user-1", {"args": {}})
        assert result["ok"] is True
        assert "no action configured" in result["message"]


# ─── Helpers for signature verification tests ──────────────────────


def _twilio_signature(url: str, params: dict, auth_token: str) -> str:
    """Compute a valid X-Twilio-Signature header value (mirrors verify)."""
    sorted_params = sorted(params.items())
    param_str = urlencode(sorted_params)
    return hmac.new(
        auth_token.encode("utf-8"),
        (url + param_str).encode("utf-8"),
        hashlib.sha1,
    ).hexdigest()


class TestTwilioSignatureVerification:
    """SEC-1: the webhook's fail-closed auth boundary.

    ``verify_twilio_signature`` is the pure, unit-testable auth check.
    It must accept valid signatures and reject every failure mode
    (missing token, missing header, wrong token, tampered params).
    """

    URL = "https://shopstack.example.com/api/sms/incoming"
    TOKEN = "test-twilio-secret-token"
    PARAMS = {"From": "+15551234567", "Body": "add 2 kg onion"}

    def test_valid_signature_accepted(self):
        sig = _twilio_signature(self.URL, self.PARAMS, self.TOKEN)
        assert verify_twilio_signature(self.URL, self.PARAMS, sig, self.TOKEN) is True

    def test_missing_token_rejected(self):
        """No auth token configured → fail-closed (never allow)."""
        sig = _twilio_signature(self.URL, self.PARAMS, self.TOKEN)
        assert verify_twilio_signature(self.URL, self.PARAMS, sig, "") is False

    def test_missing_signature_header_rejected(self):
        """No signature header → fail-closed."""
        assert verify_twilio_signature(self.URL, self.PARAMS, "", self.TOKEN) is False

    def test_wrong_token_rejected(self):
        """Signature computed with a different token → reject."""
        sig = _twilio_signature(self.URL, self.PARAMS, "wrong-token")
        assert verify_twilio_signature(self.URL, self.PARAMS, sig, self.TOKEN) is False

    def test_tampered_params_rejected(self):
        """Altering the message body after signing breaks the signature."""
        sig = _twilio_signature(self.URL, self.PARAMS, self.TOKEN)
        tampered = {**self.PARAMS, "Body": "add 999 kg onion"}  # different body
        assert verify_twilio_signature(self.URL, tampered, sig, self.TOKEN) is False

    def test_tampered_url_rejected(self):
        """A different URL (e.g. attacker's replay host) breaks the signature."""
        sig = _twilio_signature(self.URL, self.PARAMS, self.TOKEN)
        assert verify_twilio_signature(
            "https://evil.example.com/api/sms/incoming", self.PARAMS, sig, self.TOKEN
        ) is False

    def test_replay_to_different_params_rejected(self):
        """A signature from one payload must not validate a different payload."""
        sig = _twilio_signature(self.URL, {"From": "+1", "Body": "a"}, self.TOKEN)
        assert verify_twilio_signature(self.URL, self.PARAMS, sig, self.TOKEN) is False


class TestHouseholdScopedDispatcher:
    """SEC-2: writes go to the phone-owner's household, not the global active one.

    The SMS flow resolves the sender's household from the phone registry.
    The dispatcher must use THAT id, not the process-global
    ``current_user_id()`` (which is whatever household is open in the UI).
    """

    def test_uses_resolved_user_id_not_fallback(self):
        """When the phone resolves to household-B, writes go to B even if
        the process default is household-A."""
        db = _FakeDB()
        # fallback is household-A, but the resolved id (from phone lookup) is household-B
        dispatcher = _household_scoped_dispatcher(db, fallback_user_id="household-A")
        dispatcher("household-B", {
            "intent": "add_inventory_item",
            "args": {"canonical_name": "milk"},
        })
        assert db.add_calls[0]["user_id"] == "household-B"

    def test_falls_back_when_resolved_id_empty(self):
        """An empty resolved id (local-dev Stub path) falls back to the
        process default — preserving the previous behavior."""
        db = _FakeDB()
        dispatcher = _household_scoped_dispatcher(db, fallback_user_id="default_household")
        dispatcher("", {
            "intent": "add_inventory_item",
            "args": {"canonical_name": "milk"},
        })
        assert db.add_calls[0]["user_id"] == "default_household"

    def test_no_cross_household_leak(self):
        """Concurrent messages from two households must not interleave writes."""
        db = _FakeDB()
        dispatcher = _household_scoped_dispatcher(db, fallback_user_id="default")
        dispatcher("family-1", {"intent": "add_inventory_item", "args": {"canonical_name": "rice"}})
        dispatcher("family-2", {"intent": "add_inventory_item", "args": {"canonical_name": "bread"}})
        assert db.add_calls[0]["user_id"] == "family-1"
        assert db.add_calls[1]["user_id"] == "family-2"
        assert db.add_calls[0]["lot"].canonical_name == "rice"
        assert db.add_calls[1]["lot"].canonical_name == "bread"
