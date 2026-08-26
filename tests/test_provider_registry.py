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


def test_openai_backend_can_supply_the_canonical_ocr_contract(monkeypatch):
    from shopstack.providers import registry as registry_mod

    class FakeOpenAIOCRProvider:
        name = "openai"
        backend = "openai"
        available = True
        capabilities = {"ocr", "vision"}

        def __init__(self, **_kwargs):
            pass

    monkeypatch.setattr(
        registry_mod._PROVIDER_SPECS["openai"],
        "loader",
        lambda: FakeOpenAIOCRProvider,
    )
    settings = Settings(_env_file=None, off_the_grid=False, ocr_backend="openai")
    registry = ProviderRegistry(settings)

    assert isinstance(registry.ocr, FakeOpenAIOCRProvider)
    assert registry.ocr.capabilities == {"ocr", "vision"}


def test_off_the_grid_blocks_cloud_backends(monkeypatch):
    from shopstack.providers import registry as registry_mod

    def _fail_loader():
        raise AssertionError("cloud loader should not run when off-grid")

    monkeypatch.setattr(registry_mod._PROVIDER_SPECS["openai"], "loader", _fail_loader)
    settings = Settings(_env_file=None, off_the_grid=True, planner_backend="openai")
    registry = ProviderRegistry(settings)
    planner = registry.planner
    assert planner is not None
    listed = registry.list_providers()
    planner_row = next(row for row in listed if row["name"] == "planner")
    assert planner_row["status"] == "blocked_off_grid"
    assert planner_row["available"] is False


def test_off_the_grid_allows_local_backends(monkeypatch):
    from shopstack.providers import registry as registry_mod

    class FakeMiniCPM5Provider:
        name = "minicpm5"
        backend = "minicpm5"
        available = True
        model_id = "openbmb/MiniCPM5-1B"
        parameter_count = 1.0
        capabilities = {"text", "planning"}

    monkeypatch.setattr(registry_mod._PROVIDER_SPECS["minicpm5"], "loader", lambda: FakeMiniCPM5Provider)
    settings = Settings(_env_file=None, off_the_grid=True, planner_backend="minicpm5")
    registry = ProviderRegistry(settings)
    planner = registry.planner
    assert type(planner).__name__ in ("FakeMiniCPM5Provider", "MiniCPM5Provider")
    assert planner.available is True
    assert "planning" in planner.capabilities


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
    assert registry.promptable_segmentation is not None
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
