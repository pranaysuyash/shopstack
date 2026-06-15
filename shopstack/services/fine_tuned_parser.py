"""Fine-tuned command parser — Phase 6 #16.

The MockToolCallParser in :mod:`shopstack.providers.mock_providers`
parses commands by substring matching — fine for tests, brittle in
real life ("add tomato" → intent:add_inventory_item, but
"tomato is on the list" is wrong).

This module is the *data + training* side of a real fine-tuned
parser. It ships:

1. **Training data builder** (:func:`build_training_pairs`) —
   expands a small set of seed utterances into a synthetic
   training set of (utterance, intent) pairs. The seeds cover
   the five core intents (add_inventory_item, remove_from_list,
   consume_item, move_item, find_item) in English + Hindi +
   Hinglish. Deterministic, no LLM, no internet.

2. **Tiny-LLM intent classifier** (:func:`classify_intent`) —
   given an utterance and a feature vector (length, has_number,
   has_hindi_token, has_keyword), returns the most likely
   intent. This is a *rules engine* (keyword weights + length
   heuristics + small boost for Hindi-mixed text). It's not a
   neural net — but it improves over the substring matcher by
   handling disambiguation and quantity/unit extraction.

3. **JSONL training data exporter** (:func:`export_training_jsonl`)
   — writes the synthetic pairs to disk in the standard
   ``{"text": ..., "label": ...}`` format. Future work: feed this
   to a small HuggingFace transformer fine-tune.

**Why not just call an LLM:**

Two reasons:
- The user explicitly wants *local* (no API cost, no data leak).
- The intents are stable and the action space is small (5 core
  intents). A rules engine with ~30 keyword features is enough
  to cover the 80% case. The remaining 20% can be served by a
  "sorry, I didn't understand — please rephrase" path that
  falls through to the LLM if available.

The data-side of the fine-tune (the JSONL file) is what makes
this *future-proof*: when a real LLM fine-tune runs, the data
is already there.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# ─── Canonical intents (must match tool calls in tools/) ──────────


CANONICAL_INTENTS: tuple[str, ...] = (
    "add_inventory_item",
    "remove_from_list",
    "consume_item",
    "move_item",
    "find_item",
    "general_query",
)


# ─── Keyword maps (English + Hindi/Hinglish) ───────────────────────


# Action keywords → intent
# Order matters: more specific phrases first.
ADD_KEYWORDS: tuple[str, ...] = (
    "add", "kharid", "kharidna", "kharidni", "leni hai", "lena hai",
    "add karo", "add kar", "lena", "kharidna hai", "lena padega",
)
REMOVE_KEYWORDS: tuple[str, ...] = (
    "remove", "hata", "hata do", "hatao", "delete", "nikal do", "nikalo",
)
CONSUME_KEYWORDS: tuple[str, ...] = (
    "consume", "use", "used", "kha", "kha liya", "kha liye", "khatam",
    "finish", "finished",
)
MOVE_KEYWORDS: tuple[str, ...] = (
    "move", "rakh", "rakha", "shift", "daal", "daal do", "daal diya",
    "rakh do",
)
FIND_KEYWORDS: tuple[str, ...] = (
    "find", "where", "kahan", "kaha", "hai kya", "kitna",
    "is there", "do we have", "ghar pe", "ghar mein",
)


# Unit keywords for the "add" intent
UNIT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "kg":    ("kg", "kilo", "kilogram", "किलो"),
    "g":     ("grams", "gram", "gm"),
    "L":     ("litre", "liter", "ltr", "l"),
    "ml":    ("ml", "millilitre"),
    "dozen": ("dozen"),
    "pack":  ("pack", "packet", "पैकेट"),
    "unit":  ("piece", "pieces", "qty", "quantity", "count"),
}


# Quantity patterns: digits, decimals, Hindi numerals
_DIGIT_RE = re.compile(r"(\d+(?:\.\d+)?)")
_HINDI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def _to_ascii_digits(s: str) -> str:
    return s.translate(_HINDI_DIGITS)


# ─── Feature extraction ────────────────────────────────────────────


@dataclass
class IntentFeatures:
    """Numeric features extracted from an utterance."""

    length: int = 0
    has_number: bool = False
    has_hindi: bool = False
    add_score: float = 0.0
    remove_score: float = 0.0
    consume_score: float = 0.0
    move_score: float = 0.0
    find_score: float = 0.0
    found_units: list[str] = field(default_factory=list)
    found_numbers: list[float] = field(default_factory=list)


def extract_features(utterance: str) -> IntentFeatures:
    """Extract a small numeric feature vector from ``utterance``.

    The features are designed to be:
    - Cheap to compute (regex + string ops only, no model call).
    - Locale-aware (Hindi / Devanagari handled via the
      ``_HINDI_DIGITS`` translation table).
    - Stable across punctuation and capitalization.
    """
    f = IntentFeatures()
    if not utterance:
        return f
    raw = utterance.lower().strip()
    f.length = len(raw)
    ascii_text = _to_ascii_digits(raw)
    # Numbers
    nums = _DIGIT_RE.findall(ascii_text)
    if nums:
        f.has_number = True
        try:
            f.found_numbers = [float(n) for n in nums]
        except ValueError:
            f.found_numbers = []
    # Hindi script presence (rough heuristic)
    f.has_hindi = any(0x0900 <= ord(c) <= 0x097F for c in raw)
    # Keyword scores (count of keyword matches × 1.0; capped at 3)
    f.add_score = min(3.0, sum(1.0 for k in ADD_KEYWORDS if k in raw))
    f.remove_score = min(3.0, sum(1.0 for k in REMOVE_KEYWORDS if k in raw))
    f.consume_score = min(3.0, sum(1.0 for k in CONSUME_KEYWORDS if k in raw))
    f.move_score = min(3.0, sum(1.0 for k in MOVE_KEYWORDS if k in raw))
    f.find_score = min(3.0, sum(1.0 for k in FIND_KEYWORDS if k in raw))
    # Units
    for unit, kws in UNIT_KEYWORDS.items():
        if any(k in raw for k in kws):
            f.found_units.append(unit)
    return f


# ─── Classification ───────────────────────────────────────────────


def classify_intent(utterance: str) -> dict[str, Any]:
    """Classify the intent of ``utterance`` into one of the 6 canonical intents.

    Returns a dict shaped like the provider output::

        {
            "intent": "add_inventory_item" | ...,
            "tool": "<same>",
            "args": {...},
            "confidence": float,       # 0..1
            "requires_confirmation": True,
            "raw_utterance": str,
            "features": { ... },      # extracted features for debugging
        }
    """
    feats = extract_features(utterance)
    raw = (utterance or "").strip()

    # Pick the intent with the highest score; tiebreak by length
    # (longer utterances are usually more specific).
    scores = {
        "add_inventory_item": feats.add_score,
        "remove_from_list":   feats.remove_score,
        "consume_item":       feats.consume_score,
        "move_item":          feats.move_score,
        "find_item":          feats.find_score,
    }
    best_intent, best_score = max(scores.items(), key=lambda kv: (kv[1], feats.length))
    if best_score <= 0:
        intent = "general_query"
        confidence = 0.4
    else:
        intent = best_intent
        # Confidence scales with the score, capped at 0.95
        confidence = min(0.95, 0.5 + 0.15 * best_score)
    # Boost confidence for explicit "add karo" / "kharidna hai" patterns
    if intent == "add_inventory_item" and feats.has_number:
        confidence = min(0.95, confidence + 0.1)
    if intent == "consume_item" and "khatam" in raw.lower():
        confidence = min(0.95, confidence + 0.1)

    # Args
    args: dict[str, Any] = {}
    if intent == "add_inventory_item":
        # Pick the first number as quantity, first unit as the unit.
        qty = feats.found_numbers[0] if feats.found_numbers else 1.0
        unit = feats.found_units[0] if feats.found_units else "unit"
        # Strip keywords to surface the item name (best-effort)
        item = _strip_keywords(raw)
        args = {
            "canonical_name": item or "unknown",
            "display_name": item,
            "quantity": qty,
            "unit": unit,
        }
    elif intent == "remove_from_list":
        args = {"item": _strip_keywords(raw) or "unknown"}
    elif intent == "consume_item":
        qty = feats.found_numbers[0] if feats.found_numbers else 1.0
        unit = feats.found_units[0] if feats.found_units else "unit"
        args = {
            "canonical_name": _strip_keywords(raw) or "unknown",
            "quantity": qty,
            "unit": unit,
        }
    elif intent == "move_item":
        args = {
            "item": _strip_keywords(raw) or "unknown",
            "to_location": "pantry",
        }
    elif intent == "find_item":
        args = {"query": raw}
    else:
        args = {"query": raw}

    return {
        "intent": intent,
        "tool": intent,
        "args": args,
        "confidence": round(confidence, 3),
        "requires_confirmation": True,
        "raw_utterance": raw,
        "features": {
            "length": feats.length,
            "has_number": feats.has_number,
            "has_hindi": feats.has_hindi,
            "scores": scores,
        },
    }


def _strip_keywords(text: str) -> str:
    """Best-effort: remove known keywords + numbers + units from ``text``.

    What gets stripped:
    - Action keywords (add, kharid, remove, hata, etc.).
    - Digits (ASCII + Devanagari → ASCII).
    - Unit keywords (kg, kilo, litre, packet, etc.).

    What stays: anything else, which is the *item name* the
    user mentioned (e.g. "tomato", "besan", "shimla mirch").
    """
    raw = text.lower()
    all_kws: list[str] = []
    for grp in (ADD_KEYWORDS, REMOVE_KEYWORDS, CONSUME_KEYWORDS, MOVE_KEYWORDS, FIND_KEYWORDS):
        all_kws.extend(grp)
    for unit_kws in UNIT_KEYWORDS.values():
        all_kws.extend(unit_kws)
    out = _to_ascii_digits(raw)
    for kw in all_kws:
        out = re.sub(r"\b" + re.escape(kw) + r"\b", " ", out)
    # Drop any leftover numbers
    out = re.sub(r"\b\d+(?:\.\d+)?\b", " ", out)
    out = re.sub(r"\s+", " ", out).strip(" .,;:-")
    return out


# ─── Synthetic training data ───────────────────────────────────────


# Seed templates per intent. Each template has a placeholder for
# the item name so the same template can produce many rows.
SEED_TEMPLATES: dict[str, tuple[str, ...]] = {
    "add_inventory_item": (
        "add {item}",
        "kharidna hai {item}",
        "{item} lena hai",
        "add karo {item}",
        "{item} add karo",
        "kharid {item}",
        "{item} kharidna hai",
        "aadha kilo {item} lena hai",
        "ek packet {item} add karo",
        "lena padega {item}",
        "{item} le aana",
    ),
    "remove_from_list": (
        "remove {item}",
        "hata do {item}",
        "{item} hata do",
        "delete {item}",
        "{item} nikal do list se",
        "hatao {item}",
    ),
    "consume_item": (
        "consume {item}",
        "{item} kha liya",
        "khatam {item}",
        "used {item}",
        "{item} khatam ho gaya",
        "{item} finish",
    ),
    "move_item": (
        "move {item}",
        "{item} rakh do",
        "{item} shift karo",
        "rakh {item} fridge mein",
        "{item} daal do pantry mein",
    ),
    "find_item": (
        "find {item}",
        "kahan hai {item}",
        "{item} hai kya",
        "do we have {item}",
        "{item} ghar pe hai kya",
        "kitna {item} hai",
    ),
    "general_query": (
        "what's the weather",
        "how are you",
        "tell me a joke",
        "hi",
        "hello",
        "thanks",
    ),
}


# A small seed list of canonical items. In production this would
# come from the household's pantry; for synthetic data we use a
# fixed 30-item list that covers common Indian household items.
SEED_ITEMS: tuple[str, ...] = (
    "tomato", "onion", "potato", "rice", "milk", "bread", "eggs",
    "butter", "curd", "dal", "cooking oil", "salt", "sugar", "tea",
    "coffee", "soap", "shampoo", "toothpaste", "detergent", "spinach",
    "carrot", "apple", "banana", "chicken", "fish", "paneer", "ghee",
    "wheat flour", "biscuit", "noodles",
)


def build_training_pairs() -> list[dict[str, str]]:
    """Build the synthetic training set of (text, label) pairs.

    Returns a list of ``{"text": ..., "label": ...}`` dicts. The
    size is roughly ``sum(len(templates) for templates) ×
    len(SEED_ITEMS)`` (except for ``general_query`` which has no
    item placeholder).
    """
    out: list[dict[str, str]] = []
    for intent, templates in SEED_TEMPLATES.items():
        if intent == "general_query":
            for tmpl in templates:
                out.append({"text": tmpl, "label": intent})
            continue
        for tmpl in templates:
            for item in SEED_ITEMS:
                text = tmpl.format(item=item)
                out.append({"text": text, "label": intent})
    return out


# ─── Export ────────────────────────────────────────────────────────


def export_training_jsonl(
    out_path: str | Path = "data/parser_training.jsonl",
    pairs: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Write the synthetic training pairs to a JSONL file.

    Returns a summary dict with the path, row count, and label
    distribution. Creates the parent directory if it doesn't
    exist.
    """
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = pairs if pairs is not None else build_training_pairs()
    label_counts: dict[str, int] = {}
    with open(p, "w", encoding="utf-8") as fh:
        for row in rows:
            text = row.get("text", "")
            label = row.get("label", "general_query")
            label_counts[label] = label_counts.get(label, 0) + 1
            fh.write(json.dumps({"text": text, "label": label}, ensure_ascii=False) + "\n")
    return {
        "path": str(p),
        "rows": len(rows),
        "label_distribution": label_counts,
    }


# ─── HTML rendering ───────────────────────────────────────────────


def render_intent_html(parsed: dict[str, Any]) -> str:
    """Render the parsed intent as a small explainer block.

    Shows the predicted intent, confidence, and the args that
    would be passed to the tool. Used in the Ask panel and
    Planner screen so the user can see what the parser decided.
    """
    intent = parsed.get("intent", "general_query")
    confidence = parsed.get("confidence", 0.0)
    raw = parsed.get("raw_utterance", "")
    color = "var(--green, #176B49)" if confidence >= 0.7 else (
        "var(--amber, #A76012)" if confidence >= 0.4 else "var(--red, #A63F31)"
    )
    args = parsed.get("args", {})
    args_html = "".join(
        f"<span class='ic-arg'>{escape(str(k))} = <code>{escape(str(v))}</code></span>"
        for k, v in args.items()
    )
    return (
        "<div class='ic-block'>"
        f"<div class='ic-raw'>{escape(raw)}</div><div class='ic-intent'>"
        f"<span class='ic-label'>Intent:</span> <code>{escape(intent)}</code>"
        f"<span class='ic-conf' style='color:{color};'> · {confidence * 100:.0f}%</span>"
        f"</div><div class='ic-args'>{args_html}</div>"
        f"</div>"
    )


__all__ = [
    "ADD_KEYWORDS",
    "CANONICAL_INTENTS",
    "CONSUME_KEYWORDS",
    "FIND_KEYWORDS",
    "IntentFeatures",
    "MOVE_KEYWORDS",
    "REMOVE_KEYWORDS",
    "SEED_ITEMS",
    "SEED_TEMPLATES",
    "UNIT_KEYWORDS",
    "build_training_pairs",
    "classify_intent",
    "export_training_jsonl",
    "extract_features",
    "render_intent_html",
]
