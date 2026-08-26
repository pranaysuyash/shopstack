#!/usr/bin/env python3
"""Run bounded OpenAI capability checks against existing ShopStack surfaces.

This is an evaluation harness, not a production provider switch. It uses the
ambient ``OPENAI_API_KEY`` or ``SHOPSTACK_OPENAI_API_KEY`` already configured
for the process and never writes credentials to artifacts.

The benchmark intentionally measures three separate contracts:

* Vision: strict JSON extraction using the canonical product-shelf prompt.
* Embeddings: retrieval quality through ``ShopFindService`` and its normal
  inventory data path, with caching to avoid repeated document billing.
  The corpus includes direct positives, hard-negative ranking cases, and
  explicit no-match abstention cases.
* Field-contract readiness: whether each structured product record contains
  the fields required by downstream normalization. This is not OCR accuracy
  because the image fixtures are not labeled ground truth.
* Receipt normalization: whether labeled receipt text becomes the structured
  fields expected by ``parse_receipt_text``. This is not image OCR.

Usage:
    uv run python scripts/eval_openai_capabilities.py
    uv run python scripts/eval_openai_capabilities.py --skip-vision

The default artifact is ``Docs/evals/openai_capability_benchmark_latest.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import re
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from shopstack.prompts import get_prompt
from shopstack.prompts.ocr import RECEIPT_STRUCTURED_NORMALIZATION_PROMPT
from shopstack.prompts.vision import UNDERSTAND_PRODUCT_SHELF_PROMPT
from shopstack.eval.retrieval_corpus import build_retrieval_corpus, validate_retrieval_corpus

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO / "Docs/evals/openai_capability_benchmark_latest.json"
MODEL = os.environ.get("SHOPSTACK_EVAL_MODEL", "gpt-5.6-luna")
VISION_PROMPT = UNDERSTAND_PRODUCT_SHELF_PROMPT
VISION_PROMPT_META = get_prompt("vision.understand_product_shelf")
RETRIEVAL_CORPUS = build_retrieval_corpus()
QUERIES = tuple(
    (case.query, case.expected, case.category)
    for case in RETRIEVAL_CORPUS
    if not case.no_match and not case.hard_negatives
)
NO_MATCH_QUERIES = tuple(
    (case.query, "no_match") for case in RETRIEVAL_CORPUS if case.no_match
)

FIXTURES = {
    "fresh_mart": REPO / "data/fresh_mart.png",
    "sai_pharma": REPO / "data/sai_pharma.png",
    "maa_laxmi": REPO / "data/maa_laxmi.png",
}

RECEIPT_PROMPT = RECEIPT_STRUCTURED_NORMALIZATION_PROMPT
RECEIPT_PROMPT_META = get_prompt("ocr.receipt_structured_normalization")

# Explicit synthetic labels exercise the structured normalization contract.
# They are intentionally separate from the exported receipt history because
# exported parsed output is not independent ground truth for model quality.
RECEIPT_CASES: list[dict[str, Any]] = [
    {
        "id": "single_milk",
        "text": "Demo Mart\nDate: 2026-06-06\nMilk 2 L 120\nTotal: 120.00",
        "expected": {
            "merchant": "Demo Mart",
            "purchase_date": "2026-06-06",
            "total": 120.0,
            "lines": [{"canonical_name": "milk", "quantity": 2.0, "unit": "L", "price": 120.0}],
        },
    },
    {
        "id": "multi_item_grocery",
        "text": "Fresh Mart\nDate: 2026-06-15\nMilk 2 L 120\nFlour 5 kg 250\nTomato 1 kg 40\nSugar 1 kg 45\nTotal: 455.00",
        "expected": {
            "merchant": "Fresh Mart",
            "purchase_date": "2026-06-15",
            "total": 455.0,
            "lines": [
                {"canonical_name": "milk", "quantity": 2.0, "unit": "L", "price": 120.0},
                {"canonical_name": "flour", "quantity": 5.0, "unit": "kg", "price": 250.0},
                {"canonical_name": "tomato", "quantity": 1.0, "unit": "kg", "price": 40.0},
                {"canonical_name": "sugar", "quantity": 1.0, "unit": "kg", "price": 45.0},
            ],
        },
    },
]


def _json_candidate(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """Parse strict JSON and tolerate only a surrounding markdown fence."""
    candidate = (text or "").strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.IGNORECASE)
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            return None, "no_json_object"
        try:
            value = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError as exc:
            return None, f"invalid_json:{exc.msg}"
    if not isinstance(value, dict):
        return None, "root_not_object"
    return value, None


def _validate_products(value: dict[str, Any] | None) -> dict[str, Any]:
    products = value.get("products") if value else None
    if not isinstance(products, list):
        return {"valid": False, "product_count": 0, "invalid_items": 1, "names": []}
    invalid = 0
    names: list[str] = []
    required_complete = 0
    full_contract_complete = 0
    for item in products:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            invalid += 1
            continue
        names.append(item["name"].strip())
        required = ("name", "quantity", "unit")
        if all(key in item for key in required):
            required_complete += 1
        if all(key in item for key in (*required, "brand", "price_rupees", "expiry_date")):
            full_contract_complete += 1
    return {
        "valid": invalid == 0,
        "product_count": len(products),
        "invalid_items": invalid,
        "names": names,
        "required_field_complete_count": required_complete,
        "full_contract_complete_count": full_contract_complete,
    }


def _display_path(path: Path) -> str:
    """Return a stable repo-relative path, or an absolute test path."""
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


@contextmanager
def _isolated_application_db(path: str):
    """Force an evaluation DB temporarily, then restore the caller's setting."""
    existing = os.environ.get("SHOPSTACK_DB_PATH")
    os.environ["SHOPSTACK_DB_PATH"] = path
    try:
        yield
    finally:
        if existing is None:
            os.environ.pop("SHOPSTACK_DB_PATH", None)
        else:
            os.environ["SHOPSTACK_DB_PATH"] = existing


class CachedEmbeddingProvider:
    """Cache one provider's exact input batches while preserving its API."""

    def __init__(self, provider: Any):
        self.provider = provider
        self.name = provider.name
        self.capabilities = provider.capabilities
        self.available = provider.available
        self._cache: dict[tuple[str, ...], list[list[float]]] = {}
        self.api_calls = 0
        self.total_cost_usd = 0.0
        self.call_latencies_ms: list[float] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        key = tuple(texts)
        if key not in self._cache:
            self._cache[key] = self.provider.embed(texts)
            self.api_calls += 1
            metadata = getattr(self.provider, "last_embedding_meta", {})
            cost = metadata.get("cost", {}) if isinstance(metadata, dict) else {}
            if isinstance(cost, dict):
                self.total_cost_usd += float(cost.get("usd", 0.0) or 0.0)
                if cost.get("latency_ms") is not None:
                    self.call_latencies_ms.append(float(cost["latency_ms"]))
        return self._cache[key]

    def similarity(self, left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left or not right:
            return 0.0
        numerator = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _seed_inventory(db: Any) -> str:
    from shopstack.tools.registry import ToolRegistry

    household = "openai_capability_eval"
    db.add_household(household, "OpenAI capability evaluation")
    db.add_household_member(household, household, role="owner")
    tools = ToolRegistry(db)
    lots = [
        ("milk", 2.0, "L", "fridge"),
        ("rice", 5.0, "kg", "pantry"),
        ("dal", 1.0, "kg", "pantry"),
        ("eggs", 12.0, "unit", "fridge"),
        ("onion", 2.0, "kg", "pantry"),
        ("tomato", 1.0, "kg", "pantry"),
        ("bread", 1.0, "loaf", "fridge"),
        ("curd", 0.5, "kg", "fridge"),
        ("potato", 3.0, "kg", "pantry"),
        ("butter", 0.25, "kg", "fridge"),
    ]
    for name, quantity, unit, location in lots:
        tools.add_inventory_item(
            canonical_name=name,
            display_name=name.capitalize(),
            quantity=quantity,
            unit=unit,
            storage_location_id=location,
            user_id=household,
        )
    return household


def run_vision(provider: Any) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for fixture_name, path in FIXTURES.items():
        started = time.perf_counter()
        if not path.exists():
            results.append({"fixture": fixture_name, "error": "missing_fixture"})
            continue
        response = provider.analyze_image(
            str(path), VISION_PROMPT, max_tokens=768, reasoning_effort="high"
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        raw = response.get("description", "") if isinstance(response, dict) else ""
        parsed, parse_error = _json_candidate(raw if isinstance(raw, str) else "")
        shape = _validate_products(parsed)
        item: dict[str, Any] = {
            "fixture": fixture_name,
            "path": _display_path(path),
            "latency_ms": elapsed_ms,
            "model": response.get("model", MODEL) if isinstance(response, dict) else MODEL,
            "usage": response.get("usage", {}) if isinstance(response, dict) else {},
            "cost": response.get("cost", {}) if isinstance(response, dict) else {},
            "json_parse_error": parse_error,
            **shape,
        }
        if isinstance(response, dict) and response.get("error"):
            item["error"] = response["error"]
        results.append(item)
        print(f"vision {fixture_name}: valid={shape['valid']} products={shape['product_count']} latency_ms={elapsed_ms}")
    return {
        "contract": "vision.understand_product_shelf",
        "prompt_version": VISION_PROMPT_META.version,
        "prompt_hash": hashlib.sha256(VISION_PROMPT.encode("utf-8")).hexdigest()[:12],
        "fixture_count": len(results),
        "valid_json_count": sum(1 for item in results if item.get("valid")),
        "required_field_complete_count": sum(item.get("required_field_complete_count", 0) for item in results),
        "full_contract_complete_count": sum(item.get("full_contract_complete_count", 0) for item in results),
        "results": results,
        "ground_truth": "not available; validity and field shape only",
    }


def run_embeddings(provider: Any) -> dict[str, Any]:
    cached = CachedEmbeddingProvider(provider)
    corpus = RETRIEVAL_CORPUS
    corpus_errors = validate_retrieval_corpus(corpus)
    if corpus_errors:
        return {
            "contract": "ShopFindService.semantic_find_inventory_compatible",
            "error": "invalid_retrieval_corpus",
            "corpus_errors": list(corpus_errors),
        }
    with _isolated_application_db(":memory:"):
        from shopstack.persistence.database import Database
        from shopstack.services.find import ShopFindService

        db = Database(":memory:")
        household = _seed_inventory(db)
        service = ShopFindService(db, embedding_provider=cached)
        started = time.perf_counter()
        rows: list[dict[str, Any]] = []
        for case in corpus:
            result = service.semantic_find_inventory_compatible(case.query, user_id=household)
            matches = [
                str((row.get("lot", {}) or {}).get("canonical_name", "")).lower()
                for row in result.get("results", [])
            ]
            ranked_candidates = [
                {
                    "canonical_name": str((row.get("lot", {}) or {}).get("canonical_name", "")).lower(),
                    "match_score": row.get("match_score"),
                    "confidence": row.get("confidence"),
                    "match_type": row.get("match_type"),
                }
                for row in result.get("results", [])[:5]
            ]
            target_index = matches.index(case.expected) if case.expected in matches else None
            hard_negative_indices = {
                name: matches.index(name)
                for name in case.hard_negatives
                if name in matches
            }
            retrieved = case.expected in matches if case.expected else not matches
            hard_negative_ranked_above = any(
                target_index is not None and index < target_index
                for index in hard_negative_indices.values()
            )
            rows.append({
                "case_id": case.case_id,
                "query": case.query,
                "expected": case.expected,
                "category": case.category,
                "no_match_case": case.no_match,
                "hard_negatives": list(case.hard_negatives),
                "top": matches[0] if matches else None,
                "retrieved": retrieved,
                "abstained": case.no_match and not matches,
                "target_rank": target_index + 1 if target_index is not None else None,
                "hard_negative_ranked_above": hard_negative_ranked_above,
                "ranked_candidates": ranked_candidates,
                "semantic_active": bool(result.get("semantic_active")),
                "match_type": result.get("match_type"),
            })
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        db.close()
    first_embedding = next(iter(cached._cache.values()), [[]])
    dim = len(first_embedding[0]) if first_embedding and first_embedding[0] else 0
    positive_rows = [
        row for row in rows
        if not row["no_match_case"] and row["category"] != "hard_negative"
    ]
    no_match_rows = [row for row in rows if row["no_match_case"]]
    hard_negative_rows = [row for row in rows if row["category"] == "hard_negative"]
    by_category: dict[str, dict[str, int]] = {}
    for row in positive_rows:
        bucket = by_category.setdefault(row["category"], {"correct": 0, "total": 0})
        bucket["total"] += 1
        bucket["correct"] += int(row["retrieved"])
    correct = sum(int(row["retrieved"]) for row in positive_rows)
    abstained = sum(int(row["abstained"]) for row in no_match_rows)
    hard_negative_correct = sum(
        int(row["retrieved"] and not row["hard_negative_ranked_above"])
        for row in hard_negative_rows
    )
    print(
        f"embeddings {provider.name}: positive={correct}/{len(positive_rows)} "
        f"no_match_abstention={abstained}/{len(no_match_rows)} dim={dim} api_calls={cached.api_calls}"
    )
    return {
        "contract": "ShopFindService.semantic_find_inventory_compatible",
        "model": getattr(provider, "embedding_model", "unknown"),
        "dimension": dim,
        "query_count": len(positive_rows),
        "correct_retrieval_count": correct,
        "retrieval_rate_pct": round(correct / len(positive_rows) * 100, 1) if positive_rows else 0.0,
        "by_category": by_category,
        "no_match_case_count": len(no_match_rows),
        "no_match_abstention_count": abstained,
        "no_match_abstention_rate_pct": round(abstained / len(no_match_rows) * 100, 1)
        if no_match_rows else 0.0,
        "hard_negative_case_count": len(hard_negative_rows),
        "hard_negative_correct_count": hard_negative_correct,
        "hard_negative_accuracy_pct": round(hard_negative_correct / len(hard_negative_rows) * 100, 1)
        if hard_negative_rows else 0.0,
        "total_case_count": len(rows),
        "service_elapsed_ms": elapsed_ms,
        "provider_api_call_count": cached.api_calls,
        "provider_cost_usd": round(cached.total_cost_usd, 6),
        "provider_call_latency_ms": {
            "count": len(cached.call_latencies_ms),
            "mean": round(sum(cached.call_latencies_ms) / len(cached.call_latencies_ms), 2)
            if cached.call_latencies_ms else None,
        },
        "results": rows,
        "ground_truth": "synthetic inventory with explicit positive and no-match labels",
    }


def _receipt_match(actual: dict[str, Any] | None, expected: dict[str, Any]) -> dict[str, Any]:
    if not actual:
        return {"exact_match": False, "merchant_match": False, "date_match": False, "total_match": False, "line_match": False}
    merchant_match = actual.get("merchant") == expected["merchant"]
    date_match = actual.get("purchase_date") == expected["purchase_date"]
    try:
        total_match = abs(float(actual.get("total", 0.0)) - float(expected["total"])) < 0.01
    except (TypeError, ValueError):
        total_match = False
    actual_lines = actual.get("lines", [])
    expected_lines = expected["lines"]
    line_match = isinstance(actual_lines, list) and len(actual_lines) == len(expected_lines)
    if line_match:
        for actual_line, expected_line in zip(actual_lines, expected_lines):
            line_match = line_match and all(
                actual_line.get(field) == expected_line[field]
                for field in ("canonical_name", "quantity", "unit", "price")
            )
    return {
        "exact_match": merchant_match and date_match and total_match and line_match,
        "merchant_match": merchant_match,
        "date_match": date_match,
        "total_match": total_match,
        "line_match": line_match,
        "actual_line_count": len(actual_lines) if isinstance(actual_lines, list) else 0,
    }


def run_receipts(provider: Any) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for case in RECEIPT_CASES:
        started = time.perf_counter()
        response = provider.complete(
            f"{RECEIPT_PROMPT}\n\nReceipt text:\n{case['text']}",
            max_tokens=768,
            temperature=0.0,
            reasoning_effort="high",
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        raw = response.get("text", "") if isinstance(response, dict) else ""
        parsed, parse_error = _json_candidate(raw if isinstance(raw, str) else "")
        quality = _receipt_match(parsed, case["expected"])
        results.append({
            "case": case["id"],
            "latency_ms": elapsed_ms,
            "model": response.get("model", MODEL) if isinstance(response, dict) else MODEL,
            "usage": response.get("usage", {}) if isinstance(response, dict) else {},
            "cost": response.get("cost", {}) if isinstance(response, dict) else {},
            "json_parse_error": parse_error,
            "actual_merchant": parsed.get("merchant") if parsed else None,
            "actual_line_names": [line.get("canonical_name") for line in parsed.get("lines", [])]
            if parsed and isinstance(parsed.get("lines"), list) else [],
            **quality,
        })
        print(f"receipt {case['id']}: exact={quality['exact_match']} latency_ms={elapsed_ms}")
    return {
        "contract": "receipt_structured_normalization",
        "prompt_version": RECEIPT_PROMPT_META.version,
        "prompt_hash": hashlib.sha256(RECEIPT_PROMPT.encode("utf-8")).hexdigest()[:12],
        "parser_reference": "shopstack.services.receipt.parse_receipt_text",
        "case_count": len(results),
        "exact_match_count": sum(1 for item in results if item["exact_match"]),
        "results": results,
        "ground_truth": "explicit synthetic labels; text normalization only, not image OCR",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=MODEL, help="OpenAI chat/vision model")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--skip-vision", action="store_true")
    parser.add_argument("--skip-embeddings", action="store_true")
    parser.add_argument("--skip-receipts", action="store_true")
    args = parser.parse_args()

    from shopstack.providers.openai_provider import OpenAIProvider

    provider = OpenAIProvider(model=args.model)
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        revision = "unknown"
    try:
        dirty = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--"],
            cwd=REPO,
            check=False,
        ).returncode != 0
    except OSError:
        dirty = None
    result: dict[str, Any] = {
        "schema_version": "1",
        "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider": provider.name,
        "model": args.model,
        "embedding_model": provider.embedding_model,
        "code_revision": revision,
        "worktree_dirty": dirty,
        "available": provider.available,
        "credential_source": "ambient environment; value never persisted",
        "surfaces": {},
    }
    if not provider.available:
        result["error"] = provider.error or "provider_unavailable"
    else:
        if not args.skip_vision:
            result["surfaces"]["vision"] = run_vision(provider)
        if not args.skip_embeddings:
            result["surfaces"]["embeddings"] = run_embeddings(provider)
        if not args.skip_receipts:
            result["surfaces"]["receipts"] = run_receipts(provider)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"artifact: {args.output}")
    return 0 if result["available"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
