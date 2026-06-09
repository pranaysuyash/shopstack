from __future__ import annotations

import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "ShopStack"
    app_description: str = "Shopping intelligence platform: know what you have, what to buy, what to skip, and where to buy from."
    app_version: str = "0.1.0"
    debug: bool = True

    off_the_grid: bool = True
    default_household_user_id: str = "default_household"
    app_port: int = 7860
    db_path: str = str(Path(__file__).resolve().parent.parent / "data" / "shopstack.db")
    data_dir: str = str(Path(__file__).resolve().parent.parent / "data")

    openai_api_key: str = ""
    hf_api_key: str = ""

    local_model_dir: str = ""
    local_model_repo: str = "unsloth/Llama-3.2-3B-Instruct-GGUF"
    local_model_file: str = "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
    local_mlx_model: str = "mlx-community/Qwen3.5-4B-4bit"
    local_auto_download: bool = True

    local_whisper_size: str = "tiny"
    local_auto_unload: bool = True
    local_whisper_auto_unload: bool = True

    trace_max_rows: int = 2000
    trace_ttl_days: int = 30

    cost_budget_limit: float = 1.00

    planner_backend: str = "local"
    stt_backend: str = "sensevoice"
    tts_backend: str = "kokoro"
    vision_backend: str = "mock"
    ocr_backend: str = "tesseract"
    segmentation_backend: str = "mock"
    image_gen_backend: str = "svg"
    embeddings_backend: str = "bge_m3"
    tool_call_parser_backend: str = "minicpm5"

    model_config = {"env_file": ".env", "env_prefix": "SHOPSTACK_", "extra": "ignore"}

    def __init__(self, **values):
        super().__init__(**values)
        # Backward-compatibility shim for the old environment variable name.
        # Prefer new SHOPSTACK_DB_PATH when explicitly set.
        legacy_db_path = os.getenv("SHOPSTACK_DATABASE_PATH")
        if legacy_db_path and "db_path" not in self.model_dump(exclude_unset=True):
            self.db_path = legacy_db_path

    @property
    def provider_backends(self) -> dict[str, str]:
        """Backward-compatible provider backend map.

        Canonical configuration is in *_backend fields (for example
        stt_backend), but existing callers may still read provider_backends.
        """
        return {
            "stt": self.stt_backend,
            "tts": self.tts_backend,
            "vision": self.vision_backend,
            "object_detection": self.vision_backend,
            "grounding": self.vision_backend,
            "segmentation": self.segmentation_backend,
            "ocr": self.ocr_backend,
            "planner": self.planner_backend,
            "tool_call_parser": self.tool_call_parser_backend,
            "embeddings": self.embeddings_backend,
            "image_edit": self.planner_backend,
            "image_gen": self.image_gen_backend,
        }

    @property
    def database_path(self) -> str:
        """Backward-compatible alias for legacy callers."""
        return self.db_path


settings = Settings()
