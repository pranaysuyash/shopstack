"""Regression tests for the missing-retailer-data suppression (2026-06-15).

The 2026-06-15 full-app audit flagged the per-boot "Failed to actively
load market source" warning for Blinkit / Zepto / DMart data that
isn't shipped. The fix is additive: the adapters are not removed
(per motto_v3 §11 — do not delete overbuilt features), but the
registry now:

* logs the FileNotFoundError at debug level (not warning),
* remembers the source as known-missing so subsequent loads
  are silent,
* exposes ``get_missing_sources()`` and ``get_available_sources()``
  so the UI can show "available but not loaded" instead of an
  error.

Evidence tier: T1 (static inspection) + T2 (this test passes).
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest


@pytest.fixture
def registry():
    """A SourceRegistry with two adapters: one with data, one without."""
    from shopstack.market.sources import SourceRegistry

    reg = SourceRegistry()

    class _FakeAdapter:
        def __init__(self, source_id: str, *, has_data: bool):
            self.source_id = source_id
            self.source_category = "test"
            self._has_data = has_data

        def load_snapshot(self):
            if not self._has_data:
                # The real adapter raises FileNotFoundError when
                # the data fixture is missing.
                raise FileNotFoundError(
                    f"No data fixture for {self.source_id}"
                )
            # Minimal snapshot — we never look at it in these tests.
            from shopstack.market.schema import MarketSnapshot
            return MarketSnapshot(
                snapshot_id=f"snap-{self.source_id}",
                source=self.source_id,
                source_category="test",
                captured_at="2026-06-15T00:00:00",
                raw_records=[],
                normalized_records=[],
            )

    reg.register("with_data", _FakeAdapter("with_data", has_data=True))
    reg.register("no_data", _FakeAdapter("no_data", has_data=False))
    return reg


def test_load_all_succeeds_for_sources_with_data(registry) -> None:
    """Sources with data fixtures load successfully."""
    loaded = registry.load_all(timeout_per_source=1.0)
    assert "with_data" in loaded
    assert "no_data" not in loaded


def test_load_all_does_not_warn_for_missing_data(
    registry, caplog: pytest.LogCaptureFixture
) -> None:
    """FileNotFoundError on a missing data fixture logs at debug,
    not warning. Per the audit, the per-boot warning was leaking
    the "not shipped yet" state as an error.
    """
    with caplog.at_level(logging.DEBUG, logger="shopstack.market.sources._registry"):
        registry.load_all(timeout_per_source=1.0)
    # No WARNING-level message about the missing source.
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not any("no_data" in r.getMessage() for r in warnings), (
        f"Missing data fixture should not log at warning level; "
        f"saw: {[r.getMessage() for r in warnings]}"
    )


def test_load_all_logs_each_missing_source_at_most_once(
    registry, caplog: pytest.LogCaptureFixture
) -> None:
    """The same source's FileNotFoundError should be logged at most
    once across multiple load_all calls (idempotent on
    ``_known_missing``).
    """
    with caplog.at_level(logging.DEBUG, logger="shopstack.market.sources._registry"):
        registry.load_all(timeout_per_source=1.0)
        caplog.clear()
        registry.load_all(timeout_per_source=1.0)
    # Second call should not log anything for no_data (already known).
    no_data_logs = [r for r in caplog.records if "no_data" in r.getMessage()]
    assert not no_data_logs, (
        f"Known-missing source should not be re-logged; "
        f"saw: {[r.getMessage() for r in no_data_logs]}"
    )


def test_get_missing_sources(registry) -> None:
    """After load_all, the missing source is exposed via
    get_missing_sources(). Sorted for stable test output.
    """
    assert registry.get_missing_sources() == []
    registry.load_all(timeout_per_source=1.0)
    assert registry.get_missing_sources() == ["no_data"]


def test_get_available_sources(registry) -> None:
    """Inverse: sources with data are in get_available_sources()."""
    assert set(registry.get_available_sources()) == {"with_data", "no_data"}
    registry.load_all(timeout_per_source=1.0)
    assert registry.get_available_sources() == ["with_data"]


def test_known_missing_persists_across_registrations(registry) -> None:
    """A re-registration of a known-missing source keeps it
    in ``_known_missing``. This prevents a fresh registration
    from re-triggering the log on the next load_all.
    """
    registry.load_all(timeout_per_source=1.0)
    assert "no_data" in registry.get_missing_sources()
    # Re-register the same source id with a different adapter.
    class _NewAdapter:
        source_id = "no_data"
        source_category = "test"
        def load_snapshot(self):
            raise FileNotFoundError("still no data")
    registry.register("no_data", _NewAdapter())
    # Should still be remembered.
    assert "no_data" in registry.get_missing_sources()
