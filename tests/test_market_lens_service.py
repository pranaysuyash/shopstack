from __future__ import annotations

import json

import pytest

from shopstack.services.market_lens import analyze_market_lens, enrich_market_prices


def test_analyze_market_lens_image_returns_decisions(providers, tool_registry):
    result = analyze_market_lens("fake-market-image.jpg", None, providers, tool_registry)

    assert result.items_found
    assert result.decisions
    assert result.analysis_json.startswith("{")
    assert result.tool_calls[0]["tool_name"] == "compare_visible_item_to_inventory"
    parsed = json.loads(result.detected_items_json)
    assert parsed["items"] == result.items_found


def test_analyze_market_lens_audio_returns_transcript(providers, tool_registry):
    result = analyze_market_lens(None, "fake-audio.wav", providers, tool_registry)

    assert result.transcript_text
    assert result.decisions == []
    assert result.tool_calls[0]["tool_name"] == "ask_shopstack"
    assert "audio_query" in result.analysis_json


def test_market_lens_tool_call_schema_is_canonical_for_visible_items(providers, tool_registry):
    result = analyze_market_lens("fake-market-image.jpg", None, providers, tool_registry)

    compare_calls = [
        call for call in result.tool_calls
        if call.get("tool_name") == "compare_visible_item_to_inventory"
    ]
    assert compare_calls, "Expected canonical compare tool calls"

    for call in compare_calls:
        args = call["args"]
        assert set(args.keys()) == {"canonical_name", "quantity", "unit"}
        assert isinstance(args["canonical_name"], str)
        assert args["canonical_name"].strip()
        assert isinstance(args["quantity"], (int, float))
        assert args["quantity"] > 0
        assert isinstance(args["unit"], str)


def test_analyze_market_lens_image_and_audio_records_stt_tool(providers, tool_registry):
    result = analyze_market_lens("fake-market-image.jpg", "fake-audio.wav", providers, tool_registry)

    tool_names = [call["tool_name"] for call in result.tool_calls]
    assert "compare_visible_item_to_inventory" in tool_names
    assert "stt.transcribe" in tool_names
    assert result.transcript_text


def test_analyze_market_lens_metadata_includes_source_mode_and_freshness(providers, tool_registry):
    result = analyze_market_lens("fake-market-image.jpg", None, providers, tool_registry)

    assert result.source_mode == "vision"
    assert result.freshness_label
    assert isinstance(result.warnings, list)


def test_analyze_market_lens_metadata_for_audio_mode(providers, tool_registry):
    result = analyze_market_lens(None, "fake-audio.wav", providers, tool_registry)

    assert result.source_mode == "audio"
    assert result.freshness_label



def test_enrich_market_prices_known_item():
    decisions = [{"canonical_name": "Tomato"}]

    enrich_market_prices(decisions)

    assert "swiggy_price" in decisions[0]
    assert "swiggy_available" in decisions[0]


def test_enrich_market_prices_unknown_item():
    decisions = [{"canonical_name": "unobtainium_99_xyz"}]

    enrich_market_prices(decisions)

    price = decisions[0].get("swiggy_price")
    available = decisions[0].get("swiggy_available")
    assert price is None or isinstance(price, (int, float))
    assert available is None or isinstance(available, bool)


def test_enrich_market_prices_empty_list():
    decisions: list[dict] = []
    enrich_market_prices(decisions)
    assert decisions == []


def test_enrich_market_prices_multiple_items():
    decisions = [
        {"canonical_name": "Tomato"},
        {"canonical_name": "Onion"},
    ]

    enrich_market_prices(decisions)

    assert len(decisions) == 2
    for item in decisions:
        assert "swiggy_price" in item
        assert "swiggy_available" in item
        assert "swiggy_size" in item


def test_enrich_market_prices_unknown_item_gets_explicit_none_fields():
    decisions = [{"canonical_name": "Unobtainium"}]

    enrich_market_prices(decisions)

    assert decisions[0]["swiggy_price"] is None
    assert decisions[0]["swiggy_price_per_kg"] is None
    assert decisions[0]["swiggy_available"] is None
    assert decisions[0]["swiggy_size"] == ""


def test_analyze_market_lens_no_input(providers, tool_registry):
    result = analyze_market_lens(None, None, providers, tool_registry)

    assert result.items_found == []
    assert result.decisions == []
    assert result.transcript_text == ""
    assert result.source_mode == "none"
    assert result.warnings


def test_analyze_market_lens_barcode_json_format(providers, tool_registry):
    result = analyze_market_lens("fake-market-image.jpg", None, providers, tool_registry)

    barcode = json.loads(result.barcode_json)
    assert isinstance(barcode, list)


def test_analyze_market_lens_ocr_fallback_when_no_detections(providers, tool_registry, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(providers.object_detection, "detect", lambda _path: [])

    result = analyze_market_lens("fake-market-image.jpg", None, providers, tool_registry)

    assert result.decisions
    assert result.decisions[0]["canonical_name"] == "Sample Product"
    assert result.tool_calls
    assert result.tool_calls[0]["tool_name"] == "compare_visible_item_to_inventory"
