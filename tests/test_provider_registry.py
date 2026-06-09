from __future__ import annotations

from shopstack.config import Settings
from shopstack.providers.registry import ProviderRegistry


def test_configured_registry_falls_back_to_mock_for_custom_backends():
    settings = Settings(_env_file=None, off_the_grid=False, planner_backend="transformers", stt_backend="transformers")
    registry = ProviderRegistry(settings)
    assert registry.stt is not None
    assert registry.vision is not None
    assert registry.planner is not None


def test_local_backend_falls_back_to_mock_when_not_available():
    settings = Settings(_env_file=None, off_the_grid=False, planner_backend="local")
    registry = ProviderRegistry(settings)
    assert registry.planner is not None


def test_off_the_grid_uses_mock_for_vision():
    settings = Settings(_env_file=None, off_the_grid=True)
    registry = ProviderRegistry(settings)
    vision = registry.vision
    assert vision is not None
    assert "vision" in vision.capabilities


def test_off_the_grid_uses_mock_for_ocr():
    settings = Settings(_env_file=None, off_the_grid=True)
    registry = ProviderRegistry(settings)
    ocr = registry.ocr
    assert ocr is not None


def test_register_overrides_default():
    settings = Settings(_env_file=None, off_the_grid=True)
    registry = ProviderRegistry(settings)

    class FakeProvider:
        capabilities = {"stt"}
    registry.register("stt", FakeProvider())
    assert isinstance(registry.stt, FakeProvider)


def test_get_returns_none_for_unknown_provider():
    settings = Settings(_env_file=None, off_the_grid=True)
    registry = ProviderRegistry(settings)
    assert registry.get("nonexistent_provider") is None


def test_supports_checks_capabilities():
    settings = Settings(_env_file=None, off_the_grid=True)
    registry = ProviderRegistry(settings)
    # Access providers to trigger lazy resolution
    _ = registry.stt
    assert registry.supports("stt") is True
    assert registry.supports("nonexistent_capability_xyz") is False


def test_list_providers_returns_resolved():
    settings = Settings(_env_file=None, off_the_grid=True)
    registry = ProviderRegistry(settings)
    _ = registry.stt
    _ = registry.vision
    listed = registry.list_providers()
    names = {p["name"] for p in listed}
    assert "stt" in names
    assert "vision" in names


def test_all_property_accessors_return_providers():
    settings = Settings(_env_file=None, off_the_grid=True)
    registry = ProviderRegistry(settings)
    assert registry.tts is not None
    assert registry.object_detection is not None
    assert registry.grounding is not None
    assert registry.segmentation is not None
    assert registry.tool_call_parser is not None
    assert registry.embeddings is not None
    assert registry.image_edit is not None
    assert registry.image_gen is not None
    assert registry.unified is not None


def test_lazy_resolution_only_resolves_once():
    settings = Settings(_env_file=None, off_the_grid=True)
    registry = ProviderRegistry(settings)
    stt1 = registry.stt
    stt2 = registry.stt
    assert stt1 is stt2
