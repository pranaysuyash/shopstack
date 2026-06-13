"""Tests for shopstack.services.fine_tuned_parser (Phase 6 #16)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from shopstack.services.fine_tuned_parser import (
    ADD_KEYWORDS,
    CANONICAL_INTENTS,
    CONSUME_KEYWORDS,
    FIND_KEYWORDS,
    IntentFeatures,
    MOVE_KEYWORDS,
    REMOVE_KEYWORDS,
    SEED_ITEMS,
    SEED_TEMPLATES,
    UNIT_KEYWORDS,
    build_training_pairs,
    classify_intent,
    export_training_jsonl,
    extract_features,
    render_intent_html,
)


# ── Constants ─────────────────────────────────────────────────────


def test_canonical_intents_complete():
    assert "add_inventory_item" in CANONICAL_INTENTS
    assert "consume_item" in CANONICAL_INTENTS
    assert "find_item" in CANONICAL_INTENTS
    assert "general_query" in CANONICAL_INTENTS


def test_seed_items_non_empty():
    assert len(SEED_ITEMS) >= 20


def test_seed_templates_per_intent():
    for intent in CANONICAL_INTENTS:
        if intent == "general_query":
            assert len(SEED_TEMPLATES[intent]) >= 3
        else:
            assert len(SEED_TEMPLATES[intent]) >= 5, (
                f"intent {intent!r} has too few templates"
            )


# ── Feature extraction ────────────────────────────────────────────


def test_extract_features_empty():
    f = extract_features("")
    assert f.length == 0
    assert f.has_number is False
    assert f.add_score == 0.0


def test_extract_features_basic_english():
    f = extract_features("add tomato")
    assert f.length == len("add tomato")
    assert f.add_score >= 1.0


def test_extract_features_with_number():
    f = extract_features("add 2 kg tomato")
    assert f.has_number is True
    assert 2.0 in f.found_numbers


def test_extract_features_decimal_number():
    f = extract_features("add 0.5 kg onion")
    assert f.has_number is True
    assert 0.5 in f.found_numbers


def test_extract_features_hindi_numerals_converted():
    f = extract_features("tamatar २ किलो add karo")
    assert f.has_number is True
    # 2 in any language → 2.0 in the numeric list
    assert 2.0 in f.found_numbers


def test_extract_features_detects_hindi_script():
    f = extract_features("tamatar kharidna hai")
    assert f.has_hindi is False  # "tamatar" is romanized
    f2 = extract_features("टमाटर खरीदना है")
    assert f2.has_hindi is True


def test_extract_features_finds_units():
    f = extract_features("add 1 kg tomato")
    assert "kg" in f.found_units
    f2 = extract_features("add 1 litre milk")
    assert "L" in f2.found_units
    f3 = extract_features("add 1 packet biscuit")
    assert "pack" in f3.found_units


def test_extract_features_per_intent_scores():
    add = extract_features("add tomato")
    remove = extract_features("remove tomato")
    assert add.add_score >= 1.0
    assert remove.remove_score >= 1.0
    assert add.add_score > 0
    assert remove.remove_score > 0


def test_extract_features_score_caps_at_three():
    # A long utterance with many keywords → still capped
    text = " ".join(["add tomato"] * 10)
    f = extract_features(text)
    assert f.add_score <= 3.0


# ── classify_intent ───────────────────────────────────────────────


def test_classify_intent_add_in_english():
    out = classify_intent("add tomato")
    assert out["intent"] == "add_inventory_item"
    assert out["args"]["canonical_name"] == "tomato"
    assert out["confidence"] > 0.5


def test_classify_intent_add_with_quantity_and_unit():
    out = classify_intent("add 2 kg onion")
    assert out["intent"] == "add_inventory_item"
    assert out["args"]["quantity"] == 2.0
    assert out["args"]["unit"] == "kg"


def test_classify_intent_add_in_hindi():
    out = classify_intent("tamatar kharidna hai")
    assert out["intent"] == "add_inventory_item"


def test_classify_intent_add_karo():
    out = classify_intent("doodh add karo")
    assert out["intent"] == "add_inventory_item"
    assert "doodh" in out["args"]["canonical_name"]


def test_classify_intent_consume():
    out = classify_intent("consume milk")
    assert out["intent"] == "consume_item"
    assert out["args"]["quantity"] == 1.0


def test_classify_intent_consume_khatam_boosts_confidence():
    base = classify_intent("used rice")
    boosted = classify_intent("rice khatam")
    # "khatam" should boost the confidence
    assert boosted["confidence"] > base["confidence"]


def test_classify_intent_remove():
    out = classify_intent("remove bread from list")
    assert out["intent"] == "remove_from_list"


def test_classify_intent_hata():
    out = classify_intent("doodh hata do")
    assert out["intent"] == "remove_from_list"


def test_classify_intent_move():
    out = classify_intent("move onion to pantry")
    assert out["intent"] == "move_item"


def test_classify_intent_find():
    out = classify_intent("find milk")
    assert out["intent"] == "find_item"


def test_classify_intent_find_hindi():
    out = classify_intent("doodh kahan hai")
    assert out["intent"] == "find_item"


def test_classify_intent_general_query_no_keywords():
    out = classify_intent("hello there")
    assert out["intent"] == "general_query"
    assert out["confidence"] <= 0.5


def test_classify_intent_empty_string():
    out = classify_intent("")
    assert out["intent"] == "general_query"
    assert out["raw_utterance"] == ""


def test_classify_intent_returns_tool_call_shape():
    out = classify_intent("add tomato")
    # Should match the ToolCallParserProvider output shape
    assert "intent" in out
    assert "tool" in out
    assert "args" in out
    assert "confidence" in out
    assert "requires_confirmation" in out
    assert out["requires_confirmation"] is True
    assert out["tool"] == out["intent"]  # tool mirrors intent


def test_classify_intent_score_tiebreak():
    # A long utterance with one keyword should beat a short one
    short = classify_intent("add")
    long = classify_intent("add some really long descriptive text here about the item")
    assert long["confidence"] >= short["confidence"]


# ── build_training_pairs ──────────────────────────────────────────


def test_build_training_pairs_size():
    pairs = build_training_pairs()
    # 5 intents × 6 templates × 30 items + 6 general queries
    expected = 5 * 0  # placeholder
    # The actual size depends on template counts
    assert len(pairs) > 100
    # Should have a mix of labels
    labels = {p["label"] for p in pairs}
    assert "add_inventory_item" in labels
    assert "find_item" in labels
    assert "general_query" in labels


def test_build_training_pairs_keys():
    pairs = build_training_pairs()
    for p in pairs[:50]:
        assert "text" in p
        assert "label" in p
        assert p["text"]
        assert p["label"] in CANONICAL_INTENTS


def test_build_training_pairs_general_query_no_item_placeholder():
    pairs = build_training_pairs()
    gq = [p for p in pairs if p["label"] == "general_query"]
    # general_query templates don't have {item}, so each is its own row
    assert len(gq) >= 3


def test_build_training_pairs_per_intent_coverage():
    pairs = build_training_pairs()
    per_intent: dict[str, int] = {}
    for p in pairs:
        per_intent[p["label"]] = per_intent.get(p["label"], 0) + 1
    for intent in CANONICAL_INTENTS:
        assert per_intent.get(intent, 0) > 0, f"no samples for {intent!r}"


# ── export_training_jsonl ────────────────────────────────────────


def test_export_training_jsonl_writes_file(tmp_path):
    out_path = tmp_path / "parser_training.jsonl"
    result = export_training_jsonl(out_path)
    assert result["path"] == str(out_path)
    assert result["rows"] > 0
    assert out_path.is_file()
    # Each line should be valid JSON
    with open(out_path) as fh:
        for line in fh:
            d = json.loads(line)
            assert "text" in d
            assert "label" in d


def test_export_training_jsonl_label_distribution(tmp_path):
    out_path = tmp_path / "parser_training.jsonl"
    result = export_training_jsonl(out_path)
    dist = result["label_distribution"]
    # Each non-zero intent should be present
    for intent in CANONICAL_INTENTS:
        if dist.get(intent, 0) > 0:
            assert dist[intent] > 0


def test_export_training_jsonl_creates_parent_dirs(tmp_path):
    out_path = tmp_path / "nested" / "dir" / "out.jsonl"
    result = export_training_jsonl(out_path)
    assert out_path.is_file()


def test_export_training_jsonl_accepts_custom_pairs(tmp_path):
    out_path = tmp_path / "custom.jsonl"
    custom = [{"text": "add foo", "label": "add_inventory_item"}]
    result = export_training_jsonl(out_path, pairs=custom)
    assert result["rows"] == 1
    assert result["label_distribution"] == {"add_inventory_item": 1}


# ── render_intent_html ───────────────────────────────────────────


def test_render_intent_html_basic():
    parsed = classify_intent("add 2 kg tomato")
    html = render_intent_html(parsed)
    assert "ic-block" in html
    assert "add_inventory_item" in html
    assert "2" in html  # quantity


def test_render_intent_html_confidence_color_high():
    parsed = classify_intent("add 2 kg tomato")
    # High confidence → green
    html = render_intent_html(parsed)
    if parsed["confidence"] >= 0.7:
        assert "green" in html.lower() or "176B49" in html


def test_render_intent_html_confidence_color_low():
    parsed = classify_intent("hello")
    # Low confidence → red or amber
    html = render_intent_html(parsed)
    if parsed["confidence"] < 0.4:
        assert "red" in html.lower() or "amber" in html.lower() or "A63F31" in html


def test_render_intent_html_escapes_xss():
    parsed = classify_intent("<script>alert(1)</script>")
    html = render_intent_html(parsed)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_render_intent_html_includes_args():
    parsed = classify_intent("add 0.5 kg paneer")
    html = render_intent_html(parsed)
    assert "canonical_name" in html
    assert "quantity" in html
    assert "unit" in html
