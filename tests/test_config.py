from __future__ import annotations

from shopstack.config import Settings


class TestSettings:
    def test_defaults(self, monkeypatch):
        monkeypatch.delenv("SHOPSTACK_OFF_THE_GRID", raising=False)
        s = Settings(_env_file=None)
        assert s.off_the_grid is True
        assert s.db_path
        assert s.app_port == 7860

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("SHOPSTACK_DB_PATH", "/tmp/test.db")
        monkeypatch.setenv("SHOPSTACK_APP_PORT", "8080")
        monkeypatch.setenv("SHOPSTACK_OFF_THE_GRID", "false")
        s = Settings(_env_file=None)
        assert s.db_path == "/tmp/test.db"
        assert s.app_port == 8080
        assert s.off_the_grid is False

    def test_provider_backends_default(self, monkeypatch):
        monkeypatch.delenv("SHOPSTACK_OFF_THE_GRID", raising=False)
        s = Settings(_env_file=None)
        assert s.stt_backend == "mock"
        assert s.tts_backend == "mock"
        assert s.vision_backend == "mock"

    def test_provider_backends_compat_alias(self):
        s = Settings(_env_file=None, stt_backend="mock", tts_backend="mock", vision_backend="mock", ocr_backend="mock")
        assert s.provider_backends["stt"] == "mock"
        assert s.provider_backends["tts"] == "mock"
        assert s.provider_backends["vision"] == "mock"

    def test_database_path_alias(self, monkeypatch):
        monkeypatch.delenv("SHOPSTACK_OFF_THE_GRID", raising=False)
        s = Settings(_env_file=None, db_path="/tmp/legacy.db")
        assert s.database_path == "/tmp/legacy.db"

    def test_legacy_env_database_path_alias(self, monkeypatch):
        monkeypatch.setenv("SHOPSTACK_DATABASE_PATH", "/tmp/legacy-env.db")
        monkeypatch.delenv("SHOPSTACK_DB_PATH", raising=False)
        s = Settings(_env_file=None)
        assert s.db_path == "/tmp/legacy-env.db"
