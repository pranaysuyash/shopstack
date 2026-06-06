from __future__ import annotations

import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "ShopStack"
    app_version: str = "0.1.0"
    debug: bool = True

    off_the_grid: bool = True
    app_port: int = 7860
    db_path: str = str(Path(__file__).resolve().parent.parent / "data" / "shopstack.db")
    data_dir: str = str(Path(__file__).resolve().parent.parent / "data")

    openai_api_key: str = ""

    planner_backend: str = "mock"
    stt_backend: str = "mock"
    tts_backend: str = "mock"
    vision_backend: str = "mock"
    ocr_backend: str = "mock"
    segmentation_backend: str = "mock"

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
            "tool_call_parser": self.planner_backend,
            "embeddings": self.planner_backend,
            "image_edit": self.planner_backend,
        }

    @property
    def database_path(self) -> str:
        """Backward-compatible alias for legacy callers."""
        return self.db_path


settings = Settings()
