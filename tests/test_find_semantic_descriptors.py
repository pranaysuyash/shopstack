from __future__ import annotations

from types import SimpleNamespace

from shopstack.services.find import SEARCH_DESCRIPTORS, ShopFindService


def test_semantic_lot_documents_include_provider_neutral_descriptors():
    lot = SimpleNamespace(
        canonical_name="butter",
        display_name="Butter",
        category="",
        status="active",
        unit="kg",
        source_event_id="",
    )
    assert "dairy spread" in ShopFindService._lot_search_text(
        lot,
        None,
    )
    assert SEARCH_DESCRIPTORS["potato"] == ("root vegetable", "starchy vegetable")
