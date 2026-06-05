from __future__ import annotations

from shopstack.config import Settings


class TestSettings:
    def test_defaults(self):
        s = Settings()
        assert s.off_the_grid is True
        assert s.db_path
        assert s.app_port == 7860

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("SHOPSTACK_DB_PATH", "/tmp/test.db")
        monkeypatch.setenv("SHOPSTACK_APP_PORT", "8080")
        monkeypatch.setenv("SHOPSTACK_OFF_THE_GRID", "false")
        s = Settings()
        assert s.db_path == "/tmp/test.db"
        assert s.app_port == 8080
        assert s.off_the_grid is False

    def test_provider_backends_default(self):
        s = Settings()
        assert s.stt_backend == "mock"
        assert s.tts_backend == "mock"
        assert s.vision_backend == "mock"
