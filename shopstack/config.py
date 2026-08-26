from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "ShopStack"
    app_description: str = "Shopping intelligence platform: know what you have, what to buy, what to skip, and where to buy from."
    app_version: str = "0.1.0"
    debug: bool = True

    ui_mode: str = "consumer"  # "consumer" | "developer" — gates developer-facing UI elements

    off_the_grid: bool = True
    default_household_user_id: str = "default_household"
    app_port: int = 7860
    db_path: str = str(Path(__file__).resolve().parent.parent / "data" / "shopstack.db")
    data_dir: str = str(Path(__file__).resolve().parent.parent / "data")

    openai_api_key: str = ""
    hf_api_key: str = ""

    # SMS / WhatsApp inbound webhook security (see services/sms_webhook.py).
    # The webhook is DISABLED by default — it only mounts when explicitly
    # enabled AND a Twilio auth token is present. This is fail-closed:
    # a public deployment without these set simply has no webhook surface,
    # so the unauthenticated-injection attack surface is zero by default.
    sms_webhook_enabled: bool = False
    twilio_auth_token: str = ""

    local_model_dir: str = ""
    local_model_repo: str = "unsloth/Llama-3.2-3B-Instruct-GGUF"
    local_model_file: str = "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
    local_mlx_model: str = "mlx-community/Ministral-8B-Instruct-2410-4bit"
    local_auto_download: bool = True

    local_whisper_size: str = "tiny"
    local_auto_unload: bool = True
    local_whisper_auto_unload: bool = True
    model_stack: str = "default"

    trace_max_rows: int = 2000
    trace_ttl_days: int = 30

    cost_budget_limit: float = 1.00

    planner_backend: str = "local"
    stt_backend: str = "sensevoice"
    tts_backend: str = "kokoro"
    vision_backend: str = "qwen3vl"
    ocr_backend: str = "glm_ocr"  # Primary OCR (GLM-OCR). Falls back to Tesseract via ocr_pipeline.py when GLM-OCR fails (e.g. on real-world photos).
    segmentation_backend: str = "birefnet"
    promptable_segmentation_backend: str = "mobile_sam"
    grounding_backend: str = "grounding_dino"
    image_gen_backend: str = "svg"
    embeddings_backend: str = "nomic"

    # Modal Labs cloud GPU provider URLs (set these to use remote GPU inference)
    # Format: https://<workspace>--<app>-<func>.modal.run
    modal_planner_url: str = ""
    modal_vision_url: str = ""
    modal_ocr_url: str = ""
    modal_embeddings_url: str = ""
    modal_stt_url: str = ""
    modal_tts_url: str = ""
    modal_segmentation_url: str = ""
    # Phase 11 #1.7: was "minicpm5" but MiniCPM5Provider does not declare
    # ``tool_call_parser`` in its capabilities (it only does text+planning).
    # The registry would fall through to MockToolCallParser anyway. Default
    # to "mock" so the registry resolves immediately and the operator
    # sees the canonical parser without a silent capability mismatch.
    # Per Docs/NOT_STARTED_FEATURES.md §1.7.
    tool_call_parser_backend: str = "mock"
    planner_compact_tools: bool = False  # Use compact type-shorthand tool descriptions (~90% accuracy vs ~50%)
    planner_allow_writes: bool = False

    model_config = {"env_file": ".env", "env_prefix": "SHOPSTACK_", "extra": "ignore"}

    def __init__(self, **values):
        super().__init__(**values)
        # Backward-compatibility shim for the old environment variable name.
        # Prefer new SHOPSTACK_DB_PATH when explicitly set.
        legacy_db_path = os.getenv("SHOPSTACK_DATABASE_PATH")
        if legacy_db_path and "db_path" not in self.model_dump(exclude_unset=True):
            self.db_path = legacy_db_path

        self._apply_model_stack_preset()

    def _apply_model_stack_preset(self) -> None:
        """Overlay a named model stack preset onto unset provider backends."""
        preset = self.model_stack.strip().lower()
        if preset != "openbmb_local":
            return

        explicit_fields = set(self.model_dump(exclude_unset=True).keys())
        preset_backends = {
            "planner_backend": "minicpm5",
            "ocr_backend": "glm_ocr",  # overrides default tesseract for vision-native OCR
        }
        # vision_backend=qwen3vl, segmentation_backend=birefnet, embeddings_backend=nomic,
        # and most other backends are now the default — no longer need explicit preset overrides.
        for field_name, backend in preset_backends.items():
            if field_name not in explicit_fields:
                setattr(self, field_name, backend)

    @property
    def provider_backends(self) -> dict[str, str]:
        """Backward-compatible provider backend map.

        Canonical configuration is in *_backend fields (for example
        stt_backend), but existing callers may still read provider_backends.
        """
        backends = {
            "stt": self.stt_backend,
            "tts": self.tts_backend,
            "vision": self.vision_backend,
            "object_detection": self.vision_backend,
            "grounding": self.grounding_backend,
            "segmentation": self.segmentation_backend,
            "promptable_segmentation": self.promptable_segmentation_backend,
            "ocr": self.ocr_backend,
            "planner": self.planner_backend,
            "tool_call_parser": self.tool_call_parser_backend,
            "embeddings": self.embeddings_backend,
            "image_edit": self.image_gen_backend,
            "image_gen": self.image_gen_backend,
        }
        return backends

    @property
    def database_path(self) -> str:
        """Backward-compatible alias for legacy callers."""
        return self.db_path


settings = Settings()
