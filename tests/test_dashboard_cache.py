"""Regression tests for the dashboard cache wiring (2026-06-14).

Before this fix, ``_DASHBOARD_CACHE`` was declared at module level
but ``build_dashboard_state`` never read from it. Every call did a
full DB scan, which made the Today tab expensive to render.

These tests verify the cache is now:
  1. Actually consulted on second call (cache hit)
  2. Invalidated when clear_dashboard_cache() is called
  3. Per-user (different users get different cached states)
  4. Per-DB-instance (test isolation: different DBs don't share cache)

Per motto_v3 §0.10 (Observability Is Delivery) and §11 (avoid
duplicate implementations), the cache should work as documented.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from shopstack.services import dashboard as dashboard_service
from shopstack.services.dashboard import (
    DashboardState,
    build_dashboard_state,
    clear_dashboard_cache,
)


class TestDashboardCache:
    """The dashboard cache must work as documented."""

    def setup_method(self):
        """Clear cache before each test for isolation."""
        clear_dashboard_cache()

    def teardown_method(self):
        """Clear cache after each test."""
        clear_dashboard_cache()

    def test_cache_is_consulted_on_second_call(self):
        """The second call to build_dashboard_state with the same
        user_id should hit the cache, not call the uncached function."""
        # Use a mock DB that doesn't actually do anything
        from datetime import date

        class FakeDB:
            def get_active_shopping_list(self, **kwargs):
                return None
            def get_inventory(self, **kwargs):
                return []
            def get_purchase_events(self, **kwargs):
                return []
            def get_preference_signals(self, **kwargs):
                return []

        db = FakeDB()
        # First call: uncached
        with patch.object(
            dashboard_service, "_build_dashboard_state_uncached",
            wraps=dashboard_service._build_dashboard_state_uncached,
        ) as mock_uncached:
            result1 = build_dashboard_state(db, [], user_id="hh-cache-test")
            assert mock_uncached.call_count == 1, (
                "First call should invoke the uncached function"
            )

            # Second call: should hit cache
            result2 = build_dashboard_state(db, [], user_id="hh-cache-test")
            assert mock_uncached.call_count == 1, (
                f"Second call should hit the cache, but the uncached "
                f"function was called {mock_uncached.call_count} times"
            )

            # Same result
            assert result1 is result2, (
                "Cached result should be the same object as the first call"
            )

    def test_cache_is_invalidated_by_clear(self):
        """clear_dashboard_cache() should force a fresh uncached call."""
        from datetime import date

        class FakeDB:
            def get_active_shopping_list(self, **kwargs):
                return None
            def get_inventory(self, **kwargs):
                return []
            def get_purchase_events(self, **kwargs):
                return []
            def get_preference_signals(self, **kwargs):
                return []

        db = FakeDB()
        with patch.object(
            dashboard_service, "_build_dashboard_state_uncached",
            wraps=dashboard_service._build_dashboard_state_uncached,
        ) as mock_uncached:
            build_dashboard_state(db, [], user_id="hh-clear-test")
            build_dashboard_state(db, [], user_id="hh-clear-test")
            assert mock_uncached.call_count == 1, (
                "Cache should have prevented the second uncached call"
            )

            clear_dashboard_cache("hh-clear-test")
            build_dashboard_state(db, [], user_id="hh-clear-test")
            assert mock_uncached.call_count == 2, (
                "After clear_dashboard_cache, the next call should "
                "re-invoke the uncached function"
            )

    def test_cache_clear_all(self):
        """clear_dashboard_cache() with no args should clear everything."""
        from datetime import date

        class FakeDB:
            def get_active_shopping_list(self, **kwargs):
                return None
            def get_inventory(self, **kwargs):
                return []
            def get_purchase_events(self, **kwargs):
                return []
            def get_preference_signals(self, **kwargs):
                return []

        db = FakeDB()
        with patch.object(
            dashboard_service, "_build_dashboard_state_uncached",
            wraps=dashboard_service._build_dashboard_state_uncached,
        ) as mock_uncached:
            build_dashboard_state(db, [], user_id="hh-1")
            build_dashboard_state(db, [], user_id="hh-2")
            assert mock_uncached.call_count == 2

            # Both should be cached now
            build_dashboard_state(db, [], user_id="hh-1")
            build_dashboard_state(db, [], user_id="hh-2")
            assert mock_uncached.call_count == 2, (
                "Both should be cached after the first two calls"
            )

            # Clear all
            clear_dashboard_cache()
            build_dashboard_state(db, [], user_id="hh-1")
            build_dashboard_state(db, [], user_id="hh-2")
            assert mock_uncached.call_count == 4, (
                "After clear_dashboard_cache() (no args), both should "
                "re-invoke the uncached function"
            )

    def test_cache_is_per_user(self):
        """Different user_ids should have separate cache entries."""
        from datetime import date

        class FakeDB:
            def get_active_shopping_list(self, **kwargs):
                return None
            def get_inventory(self, **kwargs):
                return []
            def get_purchase_events(self, **kwargs):
                return []
            def get_preference_signals(self, **kwargs):
                return []

        db = FakeDB()
        with patch.object(
            dashboard_service, "_build_dashboard_state_uncached",
            wraps=dashboard_service._build_dashboard_state_uncached,
        ) as mock_uncached:
            build_dashboard_state(db, [], user_id="hh-alice")
            build_dashboard_state(db, [], user_id="hh-bob")
            assert mock_uncached.call_count == 2, (
                "Different user_ids should NOT share cache entries"
            )
            # Both should now be cached
            build_dashboard_state(db, [], user_id="hh-alice")
            build_dashboard_state(db, [], user_id="hh-bob")
            assert mock_uncached.call_count == 2, (
                "Both should be cached after first call each"
            )

    def test_cache_is_per_db_instance(self):
        """Different DB instances should NOT share cache (test isolation)."""
        from datetime import date

        class FakeDB:
            def get_active_shopping_list(self, **kwargs):
                return None
            def get_inventory(self, **kwargs):
                return []
            def get_purchase_events(self, **kwargs):
                return []
            def get_preference_signals(self, **kwargs):
                return []

        with patch.object(
            dashboard_service, "_build_dashboard_state_uncached",
            wraps=dashboard_service._build_dashboard_state_uncached,
        ) as mock_uncached:
            db1 = FakeDB()
            db2 = FakeDB()
            build_dashboard_state(db1, [], user_id="hh-same")
            build_dashboard_state(db2, [], user_id="hh-same")
            assert mock_uncached.call_count == 2, (
                "Same user_id but different DB instances should NOT "
                "share cache (avoids test cross-contamination)"
            )

    def test_empty_user_id_does_not_collide_with_real_user(self):
        """user_id='' (empty string) should have its own cache slot,
        not collide with a real user_id."""
        from datetime import date

        class FakeDB:
            def get_active_shopping_list(self, **kwargs):
                return None
            def get_inventory(self, **kwargs):
                return []
            def get_purchase_events(self, **kwargs):
                return []
            def get_preference_signals(self, **kwargs):
                return []

        db = FakeDB()
        with patch.object(
            dashboard_service, "_build_dashboard_state_uncached",
            wraps=dashboard_service._build_dashboard_state_uncached,
        ) as mock_uncached:
            build_dashboard_state(db, [], user_id="")
            build_dashboard_state(db, [], user_id="default_household")
            assert mock_uncached.call_count == 2, (
                "Empty user_id should not collide with real user_id"
            )
