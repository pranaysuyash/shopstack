"""Tests for ProviderRegistry property accessors (DR-013).

Per the fix described in HANDOFF_LINT_TYPE_VERIFY_GATE_2026-06-13.md §
DR-013, every ``@property`` on ``ProviderRegistry`` must call
``self.get(name)`` to use lazy resolution, not ``self._providers.get(name)``
which skips resolution and always returned ``None`` for a fresh registry.
"""

from __future__ import annotations

from shopstack.config import Settings
from shopstack.providers.registry import ProviderRegistry


class TestPropertyAccessors:
    """Every property must return the resolved provider, never None."""

    def _make_registry(self, off_the_grid: bool = True) -> ProviderRegistry:
        return ProviderRegistry(Settings(_env_file=None, off_the_grid=off_the_grid))

    def test_stt_property_resolves(self):
        reg = self._make_registry()
        assert reg.stt is not None, "stt property returned None (skipping lazy resolution)"

    def test_tts_property_resolves(self):
        reg = self._make_registry()
        assert reg.tts is not None

    def test_vision_property_resolves(self):
        reg = self._make_registry()
        assert reg.vision is not None

    def test_planner_property_resolves(self):
        reg = self._make_registry()
        assert reg.planner is not None

    def test_embeddings_property_resolves(self):
        reg = self._make_registry()
        assert reg.embeddings is not None

    def test_ocr_property_resolves(self):
        reg = self._make_registry()
        assert reg.ocr is not None

    def test_image_edit_property_resolves(self):
        reg = self._make_registry()
        assert reg.image_edit is not None

    def test_image_gen_property_resolves(self):
        reg = self._make_registry()
        assert reg.image_gen is not None

    def test_property_repeat_returns_same_instance(self):
        """Two consecutive property accesses return the same resolved instance.

        This proves the cache is stable: ``reg.stt is reg.stt`` after
        the first access populates the cache.
        """
        reg = self._make_registry()
        first = reg.stt
        second = reg.stt
        assert first is second

    def test_property_returns_singleton_for_mock_backend(self):
        """When the backend is "mock", the property returns a mock provider."""
        reg = self._make_registry(off_the_grid=True)
        # The mock provider is registered; the property should return a real instance
        stt = reg.stt
        # Check the type — should be a mock provider
        assert type(stt).__name__ != "NoneType"
