from __future__ import annotations

import json

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


def test_analyze_market_lens_image_and_audio_records_stt_tool(providers, tool_registry):
    result = analyze_market_lens("fake-market-image.jpg", "fake-audio.wav", providers, tool_registry)

    tool_names = [call["tool_name"] for call in result.tool_calls]
    assert "compare_visible_item_to_inventory" in tool_names
    assert "stt.transcribe" in tool_names
    assert result.transcript_text


def test_enrich_market_prices_known_item():
    decisions = [{"canonical_name": "Tomato"}]

    result = enrich_market_prices(decisions)

    assert "swiggy_price" in result[0]
    assert "swiggy_available" in result[0]
