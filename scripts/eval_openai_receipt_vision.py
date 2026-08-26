#!/usr/bin/env python3
"""Evaluate OpenAI vision through ShopStack's receipt OCR and parser path."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from shopstack.prompts import get_prompt
from shopstack.prompts.ocr import OPENAI_RECEIPT_TEXT_EXTRACTION_PROMPT
from shopstack.services.ocr_pipeline import ReceiptOCRPipeline
from shopstack.services.receipt import parse_receipt_text

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO / "Docs/evals/openai_receipt_vision_latest.json"
EXPECTED = {
    "merchant": "Demo Mart",
    "purchase_date": "2026-08-26",
    "total": 370.0,
    "lines": [
        {"canonical_name": "milk", "quantity": 2.0, "unit": "L", "price": 120.0},
        {"canonical_name": "rice", "quantity": 5.0, "unit": "kg", "price": 250.0},
    ],
}


VARIANTS = ("baseline", "rotated", "blurred", "low_contrast")


def _render_base_fixture() -> Any:
    """Build the deterministic receipt image used by every controlled variant."""
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1100, 700), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 34)
        small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
        small = font
    rows = [
        ("Demo Mart", font),
        ("Date: 2026-08-26", small),
        ("Milk 2 L 120", small),
        ("Rice 5 kg 250", small),
        ("Total: 370.00", font),
    ]
    y = 80
    for text, row_font in rows:
        draw.text((80, y), text, fill="black", font=row_font)
        y += 95
    return image


def _write_fixture(path: Path, variant: str) -> None:
    """Write a reproducible image perturbation without changing receipt content."""
    from PIL import ImageEnhance, ImageFilter

    image = _render_base_fixture()
    if variant == "rotated":
        image = image.rotate(4, expand=True, fillcolor="white")
    elif variant == "blurred":
        image = image.filter(ImageFilter.GaussianBlur(radius=1.5))
    elif variant == "low_contrast":
        image = ImageEnhance.Contrast(image).enhance(0.35)
    elif variant != "baseline":
        raise ValueError(f"Unknown receipt fixture variant: {variant}")
    image.save(path)


def _parsed_payload(result: Any) -> dict[str, Any]:
    return {
        "merchant": result.merchant,
        "purchase_date": result.purchase_date.isoformat(),
        "total": result.total,
        "lines": [
            {
                "canonical_name": line.canonical_name,
                "quantity": line.quantity,
                "unit": line.unit,
                "price": line.price,
            }
            for line in result.lines
        ],
    }


def compare_receipt(actual: dict[str, Any], expected: dict[str, Any] = EXPECTED) -> dict[str, Any]:
    """Compare parsed fields without treating OCR output as household truth."""
    merchant_match = actual.get("merchant") == expected["merchant"]
    date_match = actual.get("purchase_date") == expected["purchase_date"]
    try:
        total_match = abs(float(actual.get("total", 0.0)) - expected["total"]) < 0.01
    except (TypeError, ValueError):
        total_match = False
    lines_match = actual.get("lines") == expected["lines"]
    return {
        "merchant_match": merchant_match,
        "date_match": date_match,
        "total_match": total_match,
        "lines_match": lines_match,
        "exact_match": merchant_match and date_match and total_match and lines_match,
    }


def run(model: str) -> dict[str, Any]:
    from shopstack.providers.openai_provider import OpenAIProvider

    provider = OpenAIProvider(model=model)
    prompt = get_prompt("ocr.openai_receipt_text_extraction")
    artifact: dict[str, Any] = {
        "schema_version": "2",
        "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider": provider.name,
        "model": model,
        "credential_source": "ambient environment; value never persisted",
        "fixture": "synthetic_receipt_image_controlled_variants",
        "fixture_variants": list(VARIANTS),
        "prompt": {
            "name": prompt.name,
            "version": prompt.version,
            "sha256": hashlib.sha256(OPENAI_RECEIPT_TEXT_EXTRACTION_PROMPT.encode("utf-8")).hexdigest(),
        },
        "mutated_household_state": False,
    }
    if not provider.available:
        artifact.update({"available": False, "error": provider.error or "provider unavailable"})
        return artifact

    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="shopstack-receipt-vision-") as temp_dir:
        pipeline = ReceiptOCRPipeline(
            primary_ocr=provider,
            fallback_ocr=None,
            enable_preprocessing=False,
        )
        for variant in VARIANTS:
            fixture_path = Path(temp_dir) / f"receipt-{variant}.png"
            _write_fixture(fixture_path, variant)
            started = time.perf_counter()
            ocr = pipeline.extract(str(fixture_path))
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            raw_text = ocr.get("text") or ocr.get("raw_text") or ""
            parsed = parse_receipt_text(raw_text) if raw_text else None
            actual = _parsed_payload(parsed) if parsed is not None else {}
            results.append({
                "variant": variant,
                "pipeline_stage": ocr.get("pipeline_stage"),
                "ocr_error": ocr.get("error"),
                "elapsed_ms": elapsed_ms,
                "latency_ms": ocr.get("latency_ms"),
                "usage": ocr.get("usage", {}),
                "cost": ocr.get("cost", {}),
                "raw_text_present": bool(raw_text),
                "parsed": actual,
                "quality": compare_receipt(actual),
            })
    exact_matches = sum(result["quality"]["exact_match"] for result in results)
    total_cost = round(sum(float(result.get("cost", {}).get("usd", 0.0) or 0.0) for result in results), 6)
    total_elapsed_ms = round(sum(float(result.get("elapsed_ms", 0.0) or 0.0) for result in results), 1)
    artifact.update({
        "available": True,
        "pipeline_contract": "ReceiptOCRPipeline -> parse_receipt_text",
        "preprocessing_enabled": False,
        "results": results,
        "summary": {
            "exact_matches": exact_matches,
            "variant_count": len(results),
            "exact_match_rate": exact_matches / len(results) if results else 0.0,
            "total_elapsed_ms": total_elapsed_ms,
            "total_cost_usd": total_cost,
        },
        "expected": EXPECTED,
        "evidence_boundary": "controlled synthetic variants; not real-world receipt-photo accuracy",
    })
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=os.environ.get("SHOPSTACK_EVAL_MODEL", "gpt-5.6-luna"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    artifact = run(args.model)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "available": artifact.get("available"), "summary": artifact.get("summary")}, sort_keys=True))
    return 0 if artifact.get("available") and artifact.get("summary", {}).get("exact_matches") == len(VARIANTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
