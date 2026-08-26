"""Offline tests for the reusable OpenAI capability evaluator."""

from __future__ import annotations

from pathlib import Path

from scripts import eval_openai_capabilities as evaluator


class FakeCapabilityProvider:
    name = "fake-capability"
    capabilities = {"vision", "embeddings"}
    available = True
    model_id = "fake-vision-v1"
    embedding_model = "fake-embedding-v1"

    def __init__(self) -> None:
        self.embed_calls = 0

    def analyze_image(self, image_path: str, prompt: str, **kwargs):
        assert prompt == evaluator.VISION_PROMPT
        return {
            "description": '{"products":[{"name":"milk","brand":"","quantity":1,"unit":"L",'
            '"price_rupees":null,"expiry_date":null}]}',
            "model": self.model_id,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "cost": {"usd": 0.0},
        }

    def complete(self, prompt: str, **kwargs):
        if "Fresh Mart" in prompt:
            payload = {
                "merchant": "Fresh Mart",
                "purchase_date": "2026-06-15",
                "total": 455.0,
                "lines": [
                    {"canonical_name": "milk", "display_name": "Milk", "quantity": 2.0, "unit": "L", "price": 120.0},
                    {"canonical_name": "flour", "display_name": "Flour", "quantity": 5.0, "unit": "kg", "price": 250.0},
                    {"canonical_name": "tomato", "display_name": "Tomato", "quantity": 1.0, "unit": "kg", "price": 40.0},
                    {"canonical_name": "sugar", "display_name": "Sugar", "quantity": 1.0, "unit": "kg", "price": 45.0},
                ],
            }
        else:
            payload = {
                "merchant": "Demo Mart",
                "purchase_date": "2026-06-06",
                "total": 120.0,
                "lines": [{"canonical_name": "milk", "display_name": "Milk", "quantity": 2.0, "unit": "L", "price": 120.0}],
            }
        return {"text": __import__("json").dumps(payload), "model": self.model_id, "usage": {}, "cost": {"usd": 0.0}}

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.embed_calls += 1
        names = ["milk", "rice", "dal", "eggs", "onion", "tomato", "bread", "curd", "potato", "butter"]
        aliases = {"doodh": "milk", "dahi": "curd", "chawal": "rice", "aloo": "potato", "anda": "eggs", "pyaaz": "onion", "tamatar": "tomato"}
        vectors = []
        for text in texts:
            lowered = text.lower()
            name = next((alias_target for alias, alias_target in aliases.items() if alias in lowered), None)
            name = name or next((item for item in names if item in lowered), "unknown")
            vector = [0.0] * len(names)
            if name in names:
                vector[names.index(name)] = 1.0
            vectors.append(vector)
        return vectors


def test_json_contract_accepts_strict_response_and_rejects_invalid_shape():
    parsed, error = evaluator._json_candidate('{"products": []}')
    assert error is None
    assert evaluator._validate_products(parsed)["valid"] is True

    parsed, error = evaluator._json_candidate("not json")
    assert parsed is None
    assert error == "no_json_object"

    assert evaluator._validate_products({"products": [{"brand": "missing name"}]})["valid"] is False


def test_vision_runner_uses_canonical_prompt_and_reports_contract(monkeypatch, tmp_path: Path):
    fixture = tmp_path / "fixture.png"
    fixture.write_bytes(b"fixture")
    monkeypatch.setattr(evaluator, "FIXTURES", {"fixture": fixture})

    result = evaluator.run_vision(FakeCapabilityProvider())

    assert result["contract"] == "vision.understand_product_shelf"
    assert result["valid_json_count"] == 1
    assert result["results"][0]["names"] == ["milk"]


def test_embedding_runner_uses_canonical_search_and_caches_documents():
    provider = FakeCapabilityProvider()

    result = evaluator.run_embeddings(provider)

    assert result["contract"] == "ShopFindService.semantic_find_inventory_compatible"
    assert result["retrieval_rate_pct"] == 100.0
    assert result["hard_negative_case_count"] == 6
    assert result["hard_negative_accuracy_pct"] == 100.0
    assert result["provider_api_call_count"] == len(evaluator.RETRIEVAL_CORPUS) + 1
    assert provider.embed_calls == result["provider_api_call_count"]
    assert result["no_match_abstention_count"] == len(evaluator.NO_MATCH_QUERIES)


def test_receipt_runner_compares_structured_output_to_explicit_labels():
    result = evaluator.run_receipts(FakeCapabilityProvider())

    assert result["contract"] == "receipt_structured_normalization"
    assert result["case_count"] == 2
    assert result["exact_match_count"] == 2


def test_isolated_application_db_overrides_and_restores_existing_environment(monkeypatch):
    monkeypatch.setenv("SHOPSTACK_DB_PATH", "/already/configured.db")

    with evaluator._isolated_application_db("/temporary-eval.db"):
        assert evaluator.os.environ["SHOPSTACK_DB_PATH"] == "/temporary-eval.db"

    assert evaluator.os.environ["SHOPSTACK_DB_PATH"] == "/already/configured.db"


def test_isolated_application_db_removes_only_its_temporary_environment(monkeypatch):
    monkeypatch.delenv("SHOPSTACK_DB_PATH", raising=False)

    with evaluator._isolated_application_db("/temporary-eval.db"):
        assert evaluator.os.environ["SHOPSTACK_DB_PATH"] == "/temporary-eval.db"

    assert "SHOPSTACK_DB_PATH" not in evaluator.os.environ
