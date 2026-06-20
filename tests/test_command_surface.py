"""Regression tests for the command surface (2026-06-15).

The command surface merges the legacy "Quick add" + "Ask ShopStack"
inputs into a single typed input. The user types one of:

* "add milk"            → add_to_list
* "i bought rice"       → log_purchase
* "we have onion"        → add_stock
* "we finished bread"    → mark_consumed
* anything else         → ask (free-form Ask ShopStack)

These tests pin the intent parser contract so the routes don't
silently change.
"""
from __future__ import annotations

from shopstack.services.command_surface import (
    COMMON_STAPLE_CHIPS,
    CommandIntent,
    parse_intent,
    _normalise_canonical_name,
)


class TestNormaliseCanonicalName:
    """Helper that converts free-text to a canonical slug."""

    def test_simple_lowercase(self):
        assert _normalise_canonical_name("Milk") == "milk"

    def test_multi_word_underscored(self):
        assert _normalise_canonical_name("Wheat Flour") == "wheat_flour"

    def test_punctuation_stripped(self):
        assert _normalise_canonical_name("Milk (1L)") == "milk_1l"

    def test_collapses_whitespace(self):
        assert _normalise_canonical_name("  toor   dal  ") == "toor_dal"

    def test_empty_returns_empty(self):
        assert _normalise_canonical_name("") == ""


class TestParseIntentAddToList:
    def test_simple_add(self):
        intent = parse_intent("add milk")
        assert intent.action == "add_to_list"
        assert intent.canonical_name == "milk"

    def test_need_synonym(self):
        intent = parse_intent("need bread")
        assert intent.action == "add_to_list"
        assert intent.canonical_name == "bread"

    def test_buy_synonym(self):
        intent = parse_intent("buy atta")
        assert intent.action == "add_to_list"
        assert intent.canonical_name == "wheat_flour" or intent.canonical_name == "atta"

    def test_get_synonym(self):
        intent = parse_intent("get eggs")
        assert intent.action == "add_to_list"
        assert intent.canonical_name == "eggs"

    def test_quantity_in_name(self):
        intent = parse_intent("add 2L milk")
        assert intent.action == "add_to_list"
        # The quantity is part of the canonical name; downstream
        # dispatchers can split it later if needed.
        assert "milk" in intent.canonical_name


class TestParseIntentLogPurchase:
    def test_i_bought(self):
        intent = parse_intent("I bought rice")
        assert intent.action == "log_purchase"
        assert intent.canonical_name == "rice"

    def test_just_bought(self):
        intent = parse_intent("just bought bread")
        assert intent.action == "log_purchase"
        assert intent.canonical_name == "bread"

    def test_bought_past_tense(self):
        intent = parse_intent("bought onion")
        assert intent.action == "log_purchase"
        assert intent.canonical_name == "onion"

    def test_purchased_synonym(self):
        intent = parse_intent("purchased cooking_oil")
        assert intent.action == "log_purchase"
        assert intent.canonical_name == "cooking_oil"


class TestParseIntentAddStock:
    def test_we_have(self):
        intent = parse_intent("we have onion")
        assert intent.action == "add_stock"
        assert intent.canonical_name == "onion"

    def test_at_home(self):
        intent = parse_intent("at home 2kg rice")
        assert intent.action == "add_stock"
        assert "rice" in intent.canonical_name

    def test_stocked_synonym(self):
        intent = parse_intent("stocked up on dal")
        assert intent.action == "add_stock"
        assert "dal" in intent.canonical_name


class TestParseIntentMarkConsumed:
    def test_we_finished(self):
        intent = parse_intent("we finished bread")
        assert intent.action == "mark_consumed"
        assert intent.canonical_name == "bread"

    def test_consume_synonym(self):
        intent = parse_intent("consume milk")
        assert intent.action == "mark_consumed"
        assert intent.canonical_name == "milk"

    def test_ate(self):
        intent = parse_intent("ate tomato")
        assert intent.action == "mark_consumed"
        assert intent.canonical_name == "tomato"


class TestParseIntentAskFallback:
    """If nothing matches, fall through to 'ask' (free-form)."""

    def test_question_mark(self):
        intent = parse_intent("do we have milk?")
        assert intent.action == "ask"
        assert intent.canonical_name == ""
        assert intent.raw == "do we have milk?"

    def test_long_sentence(self):
        intent = parse_intent("what did we buy last week?")
        assert intent.action == "ask"
        assert intent.canonical_name == ""

    def test_empty(self):
        intent = parse_intent("")
        assert intent.action == "unknown"
        assert intent.canonical_name == ""

    def test_whitespace_only(self):
        intent = parse_intent("   ")
        assert intent.action == "unknown"
        assert intent.canonical_name == ""


class TestCommonStapleChips:
    """The chip row shows 10 most common Indian household staples."""

    def test_contains_milk(self):
        assert "milk" in COMMON_STAPLE_CHIPS

    def test_contains_eggs(self):
        assert "eggs" in COMMON_STAPLE_CHIPS

    def test_contains_rice(self):
        assert "rice" in COMMON_STAPLE_CHIPS

    def test_size_is_reasonable(self):
        # 10 chips is a balance between useful and not overwhelming
        assert 5 <= len(COMMON_STAPLE_CHIPS) <= 12

    def test_all_canonical_names(self):
        for chip in COMMON_STAPLE_CHIPS:
            assert chip.replace("_", "").isalnum(), f"chip '{chip}' has unexpected chars"


class TestDispatchHandlerContract:
    """The dispatch function delegates to a registered handler.

    These tests use a stub handler (no DB) to verify the routing.
    """

    def test_dispatch_routes_to_action_handler(self):
        from shopstack.services import command_surface as cs

        def add_to_list_handler(canonical_name, *, intent=None):
            return cs.CommandResult(
                success=True,
                action="add_to_list",
                canonical_name=canonical_name,
                message=f"added: {canonical_name}",
            )

        def ask_handler(canonical_name, *, intent=None):
            return cs.CommandResult(
                success=True,
                action="ask",
                canonical_name=canonical_name,
                message=f"asked: {intent.raw if intent else canonical_name}",
            )

        cs.register_handler("add_to_list", add_to_list_handler)
        cs.register_handler("ask", ask_handler)

        # "add milk" → add_to_list handler
        intent = parse_intent("add milk")
        result = cs.dispatch(intent)
        assert result.success
        assert result.action == "add_to_list"
        assert result.canonical_name == "milk"

        # Unmatched text → ask fall-through
        intent = parse_intent("what did we buy last week?")
        result = cs.dispatch(intent)
        assert result.success
        assert result.action == "ask"
        assert intent.raw == "what did we buy last week?"


class TestBatchPreviewEmptyBoundary:
    """``batch_preview('')`` boundary test — empty input returns empty preview.

    ``_preview_for_intent`` is the internal helper behind
    ``POST /api/v1/command/preview``.  The HTTP layer rejects empty
    text at the schema level (422), but the internal function must
    gracefully produce an "unknown" preview with an empty summary.
    """

    def test_batch_preview_empty_string(self):
        from shopstack.api.v1.routers.command import _preview_for_intent

        result = _preview_for_intent("")
        assert result.original_text == ""
        assert result.intent.action == "unknown"
        assert result.intent.canonical_name == ""
        assert result.intent.raw_text == ""
        assert result.would_mutate is False
        assert result.route_kind == "unknown"
        assert result.summary == ""

    def test_batch_preview_whitespace_only(self):
        from shopstack.api.v1.routers.command import _preview_for_intent

        result = _preview_for_intent("   ")
        assert result.original_text == "   "
        assert result.intent.action == "unknown"
        assert result.intent.canonical_name == ""
        assert result.intent.raw_text == "   "
        assert result.would_mutate is False
        assert result.route_kind == "unknown"
        assert result.summary == ""
