from __future__ import annotations


def test_household_grounding_suite_has_three_real_photo_fixtures():
    from benchmarks.modal.household_grounding_shared import (
        build_household_grounding_suite,
        fixture_summary,
        validate_fixture_paths,
    )

    fixtures = build_household_grounding_suite()
    assert len(fixtures) == 3
    assert {fixture.scene_id for fixture in fixtures} == {
        "fridge_interior",
        "cupboard_interior",
        "tabletop_scene",
    }
    assert {fixture.prompt for fixture in fixtures} == {"milk bottle", "oil bottle", "banana bunch"}
    assert validate_fixture_paths(fixtures) == []

    summary = fixture_summary(fixtures)
    assert len(summary) == 3
    assert summary[0]["image_path"].endswith(".png")
