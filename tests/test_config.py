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

    def test_cost_budget_default(self, monkeypatch):
        """Default budget is $1.00 USD per session."""
        monkeypatch.delenv("SHOPSTACK_COST_BUDGET_LIMIT", raising=False)
        s = Settings(_env_file=None)
        assert s.cost_budget_limit == 1.00

    def test_cost_budget_env_override(self, monkeypatch):
        """SHELLCK_COST_BUDGET_LIMIT env var overrides the default."""
        monkeypatch.setenv("SHOPSTACK_COST_BUDGET_LIMIT", "5.50")
        s = Settings(_env_file=None)
        assert s.cost_budget_limit == 5.50

    def test_cost_budget_field_exists(self, monkeypatch):
        """The cost_budget_limit field is required for planner/engine to read it.

        This regression-pins the fix: the field was added because
        planner/engine.py reads settings.cost_budget_limit, and removing
        the field would crash at import time.
        """
        s = Settings(_env_file=None)
        assert hasattr(s, "cost_budget_limit")

    def test_provider_backends_default(self, monkeypatch):
        monkeypatch.delenv("SHOPSTACK_OFF_THE_GRID", raising=False)
        # conftest.py sets these to "mock" via os.environ.setdefault so the
        # session-scoped app import doesn't bootstrap heavy providers. Clear
        # them so we actually test the Settings defaults here.
        for var in (
            "SHOPSTACK_PLANNER_BACKEND", "SHOPSTACK_STT_BACKEND",
            "SHOPSTACK_TTS_BACKEND", "SHOPSTACK_VISION_BACKEND",
            "SHOPSTACK_OCR_BACKEND", "SHOPSTACK_SEGMENTATION_BACKEND",
            "SHOPSTACK_EMBEDDINGS_BACKEND",
        ):
            monkeypatch.delenv(var, raising=False)
        s = Settings(_env_file=None)
        assert s.stt_backend == "sensevoice"
        assert s.tts_backend == "kokoro"
        assert s.vision_backend == "qwen3vl"
        assert s.segmentation_backend == "birefnet"
        assert s.promptable_segmentation_backend == "mobile_sam"
        assert s.planner_backend == "local"
        assert s.ocr_backend == "glm_ocr"

    def test_openbmb_model_stack_preset(self, monkeypatch):
        # Clear env vars that could interfere with preset application
        monkeypatch.delenv("SHOPSTACK_PLANNER_BACKEND", raising=False)
        monkeypatch.delenv("SHOPSTACK_VISION_BACKEND", raising=False)
        monkeypatch.delenv("SHOPSTACK_SEGMENTATION_BACKEND", raising=False)
        monkeypatch.delenv("SHOPSTACK_OCR_BACKEND", raising=False)
        monkeypatch.delenv("SHOPSTACK_EMBEDDINGS_BACKEND", raising=False)
        monkeypatch.delenv("SHOPSTACK_PROMPTABLE_SEGMENTATION_BACKEND", raising=False)
        monkeypatch.delenv("SHOPSTACK_STT_BACKEND", raising=False)
        monkeypatch.delenv("SHOPSTACK_TTS_BACKEND", raising=False)
        monkeypatch.delenv("SHOPSTACK_GROUNDING_BACKEND", raising=False)
        monkeypatch.delenv("SHOPSTACK_IMAGE_GEN_BACKEND", raising=False)
        monkeypatch.delenv("SHOPSTACK_TOOL_CALL_PARSER_BACKEND", raising=False)
        s = Settings(_env_file=None, model_stack="openbmb_local")
        assert s.planner_backend == "minicpm5"
        assert s.vision_backend == "qwen3vl"
        assert s.ocr_backend == "glm_ocr"
        # The openbmb_local preset only overrides planner + ocr; other
        # backends keep their defaults (nomic embeddings, minicpm5 parser,
        # sensevoice STT). Earlier revisions of the preset pinned more
        # fields, but those have since become the defaults.
        assert s.embeddings_backend == "nomic"
        # Phase 11 #1.7: was "minicpm5" but MiniCPM5Provider does not
        # declare ``tool_call_parser`` in its capabilities set.
        # The default is now "mock" so the registry resolves
        # immediately to MockToolCallParser.
        assert s.tool_call_parser_backend == "mock"
        assert s.stt_backend == "sensevoice"

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
