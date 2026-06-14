from __future__ import annotations

from shopstack.repos.inventory import InventoryRepo
from shopstack.schemas.models import FindFeedback, HouseholdObject, ObjectNote, ObjectSighting
from shopstack.services.find import ShopFindService


def _add_location(db, location_id: str, name: str, location_type: str) -> None:
    db.conn.execute(
        "INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES (?, ?, NULL, ?, '')",
        (location_id, name, location_type),
    )
    db.conn.commit()


class TestShopFindService:
    def test_find_item_returns_explainable_likely_location(self, db):
        repo = InventoryRepo(db)
        repo.add_item("toothpaste", "Toothpaste", 1, "unit", "bathroom_cabinet", category="personal care")

        result = ShopFindService(db).find_anything("toothpaste")

        assert result.count == 1
        item = result.results[0]
        assert item.entity_type == "inventory_lot"
        assert item.location_id == "bathroom_cabinet"
        assert item.location_name == "Bathroom Cabinet"
        assert item.likely_locations[0].location_id == "bathroom_cabinet"
        assert item.evidence
        assert "mark_found" in item.actions

    def test_find_location_returns_contained_items(self, db):
        repo = InventoryRepo(db)
        repo.add_item("toothpaste", "Toothpaste", 1, "unit", "bathroom_cabinet", category="personal care")

        result = ShopFindService(db).find_anything("bathroom cabinet")

        assert result.intent == "location"
        location = next(r for r in result.results if r.entity_type == "location")
        assert location.location_id == "bathroom_cabinet"
        assert any(item["canonical_name"] == "toothpaste" for item in location.contained_items)

    def test_alias_query_finds_item_category_context(self, db):
        repo = InventoryRepo(db)
        repo.add_item("crocin", "Crocin", 1, "strip", "medicine_drawer", category="medicine")

        result = ShopFindService(db).find_anything("fever medicine")

        assert result.intent == "need"
        assert any(r.lot and r.lot["canonical_name"] == "crocin" for r in result.results)
        crocin = next(r for r in result.results if r.lot and r.lot["canonical_name"] == "crocin")
        assert crocin.match_type in {"exact", "category", "context"}

    def test_movement_trail_ranks_recent_location(self, db):
        _add_location(db, "work_desktop_below", "Work Desktop Below", "shelf")
        _add_location(db, "advays_almirah", "Advay's Almirah", "cabinet")
        repo = InventoryRepo(db)
        added = repo.add_item("advay test reports", "Advay Test Reports", 1, "file", "bedroom_wardrobe", category="document")
        lot_id = added["lot_id"]

        repo.move_item(lot_id, "work_desktop_below")
        repo.move_item(lot_id, "advays_almirah")

        result = ShopFindService(db).find_anything("advay reports")
        item = next(r for r in result.results if r.entity_type == "inventory_lot")

        assert item.location_id == "advays_almirah"
        assert len(item.movement_trail) == 2
        assert item.likely_locations[0].location_id == "advays_almirah"
        assert any(loc.location_id == "work_desktop_below" for loc in item.likely_locations)

    def test_existing_find_tool_shape_is_preserved_and_enriched(self, db):
        repo = InventoryRepo(db)
        repo.add_item("toothpaste", "Toothpaste", 1, "unit", "bathroom_cabinet", category="personal care")

        result = repo.find("toothpaste")

        assert result["count"] == 1
        row = result["results"][0]
        assert row["lot"]["canonical_name"] == "toothpaste"
        assert row["location_id"] == "bathroom_cabinet"
        assert row["location_name"] == "Bathroom Cabinet"
        assert row["evidence"]
        assert row["likely_locations"]

    def test_durable_object_uses_home_sightings_notes_and_feedback(self, db):
        _add_location(db, "work_desktop_below", "Work Desktop Below", "shelf")
        _add_location(db, "my_almirah", "My Almirah", "cabinet")
        obj = db.add_household_object(HouseholdObject(
            canonical_name="advay test reports",
            display_name="Advay Test Reports",
            object_type="document",
            category="medical document",
            owner_name="Advay",
            home_location_id="my_almirah",
            current_location_id="my_almirah",
        ))
        db.record_object_sighting(ObjectSighting(
            object_id=obj.object_id,
            location_id="work_desktop_below",
            context="hospital_visit",
            notes="After hospital visit",
        ))
        db.add_object_note(ObjectNote(
            object_id=obj.object_id,
            note_text="Hospital papers often sit on the work desktop below.",
            tags=["hospital", "advay"],
        ))

        result = ShopFindService(db).find_anything("advay reports")
        item = next(r for r in result.results if r.entity_type == "household_object")

        assert item.normal_home_location_id == "my_almirah"
        assert item.current_believed_location_id == "work_desktop_below"
        assert item.likely_locations[0].location_id == "work_desktop_below"
        assert any(e.source == "note" for e in item.evidence)
        assert "set_home_location" in item.actions

        feedback = ShopFindService(db).record_feedback(FindFeedback(
            query="advay reports",
            feedback="found",
            object_id=obj.object_id,
            suggested_location_id="my_almirah",
            actual_location_id="work_desktop_below",
        ))
        assert feedback.feedback == "found"
        assert db.get_find_feedback("advay reports")[0].actual_location_id == "work_desktop_below"

    # ── Semantic search activation ────────────────────────────────────

    def test_semantic_find_uses_embedding_provider_when_wired(self, db):
        """semantic_find_inventory_compatible ranks by cosine similarity
        when an embedding provider reports ``available=True``.

        Uses a deterministic stub provider so the test does not depend
        on a real model download.
        """
        repo = InventoryRepo(db)
        repo.add_item("paracetamol", "Crocin Pain Relief", 1, "strip", "medicine_box", category="medicine")
        repo.add_item("rice", "Basmati Rice", 5, "kg", "pantry", category="grains")

        result = ShopFindService(db, embedding_provider=_StubEmbeddingProvider()).semantic_find_inventory_compatible(
            "headache relief"
        )

        assert result["semantic_active"] is True
        # Semantic matches appear above text-only matches.
        top = result["results"][0]
        assert top["match_type"] == "semantic"
        assert top["lot"]["canonical_name"] == "paracetamol"
        assert top["match_score"] >= 0.5

    def test_semantic_find_falls_back_when_provider_unavailable(self, db):
        """When the embedding provider is unavailable, semantic_find
        degrades gracefully to text matching and reports
        ``semantic_active=False``.
        """
        repo = InventoryRepo(db)
        repo.add_item("milk", "Amul Milk", 2, "L", "fridge", category="dairy")

        result = ShopFindService(db, embedding_provider=_StubEmbeddingProvider(available=False)).semantic_find_inventory_compatible("milk")

        # Text match still works.
        assert result["count"] >= 1
        assert result["semantic_active"] is False

    def test_semantic_find_returns_empty_when_no_provider(self, db):
        """Without an embedding provider at all, semantic_find still
        serves text matches but reports ``semantic_active=False``."""
        repo = InventoryRepo(db)
        repo.add_item("milk", "Amul Milk", 2, "L", "fridge", category="dairy")

        result = ShopFindService(db).semantic_find_inventory_compatible("milk")

        assert result["count"] >= 1
        assert result["semantic_active"] is False


class _StubEmbeddingProvider:
    """Deterministic stub embedding provider for testing the wiring.

    Returns high similarity when the query is semantically related to
    the document (by simple keyword overlap), so we can test the
    integration without a real model.
    """
    name = "stub"
    capabilities = {"embeddings"}

    def __init__(self, available: bool = True):
        self._available = available

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self):
        return None

    def embed(self, texts):
        return [self._vec(t) for t in texts]

    def embed_queries(self, queries):
        return [self._vec(t) for t in queries]

    def embed_documents(self, docs):
        return [self._vec(t) for t in docs]

    def similarity(self, a, b):
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0

    def _vec(self, text: str):
        """Category-clustered vector for stub-level semantic similarity.

        Returns a one-hot-style vector over semantic categories so that
        ``similarity("headache relief", "Crocin Pain Relief")`` is high
        even though no tokens overlap — that's the whole point of
        semantic embeddings.
        """
        t = text.lower()
        # Category axes — first match wins so each text maps to one
        # dominant semantic cluster.
        if any(w in t for w in ("headache", "pain", "fever", "relief", "crocin", "paracetamol", "medicine")):
            return [1.0, 0.0, 0.0, 0.0, 0.0]
        if any(w in t for w in ("rice", "grain", "food", "staple", "basmati")):
            return [0.0, 1.0, 0.0, 0.0, 0.0]
        if any(w in t for w in ("milk", "dairy", "drink", "bread", "bakery")):
            return [0.0, 0.0, 1.0, 0.0, 0.0]
        if any(w in t for w in ("wash", "clean", "detergent", "clothes", "laundry")):
            return [0.0, 0.0, 0.0, 1.0, 0.0]
        if any(w in t for w in ("teeth", "toothpaste", "tooth", "brush")):
            return [0.0, 0.0, 0.0, 0.0, 1.0]
        return [0.1] * 5
