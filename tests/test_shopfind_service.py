from __future__ import annotations

from shopstack.repos.inventory import InventoryRepo
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
