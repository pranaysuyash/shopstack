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

    planner_backend: str = "mock"
    stt_backend: str = "mock"
    tts_backend: str = "mock"
    vision_backend: str = "mock"
    ocr_backend: str = "mock"
    segmentation_backend: str = "mock"

    model_config = {"env_file": ".env", "env_prefix": "SHOPSTACK_", "extra": "ignore"}


settings = Settings()
