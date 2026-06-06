from __future__ import annotations

from shopstack.config import Settings
from shopstack.providers.registry import ProviderRegistry


def test_configured_registry_falls_back_to_mock_for_custom_backends():
    settings = Settings(off_the_grid=False, planner_backend="transformers", stt_backend="transformers")
    registry = ProviderRegistry(settings)
    # Current bootstrap supports mock backends; unsupported providers should degrade to mock providers.
    assert registry.stt is not None
    assert registry.vision is not None
    assert registry.planner is not None


def test_local_backend_falls_back_to_mock_when_not_available():
    settings = Settings(off_the_grid=False, planner_backend="local")
    registry = ProviderRegistry(settings)
    assert registry.planner is not None
