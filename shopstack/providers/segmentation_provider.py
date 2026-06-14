from __future__ import annotations

import logging
import os
import sys
import time
from typing import Any

logger = logging.getLogger(__name__)


class RMBGSegmentationProvider:
    """Segmentation provider using RMBG-1.4 via transformers.

    Provides background removal and segmentation for item card images.
    Falls back gracefully when deps are missing.
    """

    name = "rmbg"
    model_id = "rmbg-1.4"
    parameter_count = 0.3
    license_note = "Apache-2.0"
    runtime_type = "transformers"
    supports_off_grid = True
    capabilities: set[str] = {"segmentation"}

    def __init__(
        self,
        model_name: str = "briaai/RMBG-1.4",
        device: str = "auto",
    ):
        self._model_name = model_name
        self._device = device
        self._model = None
        self._processor = None
        self._available = False
        self._error: str | None = None
        self._last_latency_ms: float | None = None
        self._init()

    def _init(self) -> None:
        try:
            import torch  # noqa: F401
            from transformers import (  # noqa: F401
                AutoModelForImageSegmentation,
                AutoImageProcessor,
            )
            self._available = True
            self._error = None
            logger.info("RMBG provider initialised (model=%s)", self._model_name)
        except ImportError:
            self._error = (
                "transformers/torch not installed. "
                "Run: uv pip install transformers torch"
            )
            self._available = False

    def load(self) -> None:
        if self._model is not None:
            return
        self._load_model()

    def _load_model(self) -> bool:
        if self._model is not None:
            return True
        try:
            import torch
            from transformers import AutoModelForImageSegmentation, AutoImageProcessor

            logger.info("Loading RMBG model %s ...", self._model_name)
            self._processor = AutoImageProcessor.from_pretrained(self._model_name)
            self._model = AutoModelForImageSegmentation.from_pretrained(
                self._model_name,
                torch_dtype=torch.bfloat16,
            )
            if self._device == "auto":
                if torch.cuda.is_available():
                    self._model = self._model.to("cuda")
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    self._model = self._model.to("mps")
            else:
                self._model = self._model.to(self._device)
            self._model.eval()
            logger.info("RMBG model loaded")
            return True
        except ImportError:
            self._error = (
                "transformers/torch not installed. "
                "Run: uv pip install transformers torch"
            )
            return False
        except Exception as e:
            self._error = f"Failed to load RMBG model: {e}"
            logger.warning("RMBG model load failed", exc_info=True)
            return False

    def segment(self, image_path: str) -> list[dict[str, Any]]:
        """Segment an image and return mask data.

        Returns a list of detected segments with masks and bounding boxes.
        For RMBG-1.4, outputs a single background-removal mask.
        """
        if not self._available:
            return [{"error": self._error or "RMBG not available"}]
        if not os.path.isfile(image_path):
            return [{"error": f"Image file not found: {image_path}"}]

        if self._model is None and not self._load_model():
            return [{"error": self._error or "Failed to load model"}]

        try:
            import torch
            from PIL import Image

            t0 = time.monotonic()

            image = Image.open(image_path).convert("RGB")
            inputs = self._processor(images=image, return_tensors="pt")
            if torch.cuda.is_available():
                inputs = {k: v.to("cuda") for k, v in inputs.items()}
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                inputs = {k: v.to("mps") for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self._model(**inputs)
                mask = torch.sigmoid(outputs.pred_masks[0, 0]).cpu().numpy()

            elapsed = time.monotonic() - t0
            self._last_latency_ms = round(elapsed * 1000, 1)

            height, width = mask.shape
            import numpy as np
            fg_pixels = np.argwhere(mask > 0.5)
            if len(fg_pixels) > 0:
                y1, x1 = fg_pixels.min(axis=0)
                y2, x2 = fg_pixels.max(axis=0)
                bbox = [
                    round(x1 / width, 3),
                    round(y1 / height, 3),
                    round(x2 / width, 3),
                    round(y2 / height, 3),
                ]
            else:
                bbox = [0.0, 0.0, 1.0, 1.0]

            return [{
                "label": "foreground",
                "score": round(float(mask.mean()), 3),
                "mask": None,
                "bbox": bbox,
                "latency_ms": self._last_latency_ms,
            }]
        except Exception as e:
            logger.warning("RMBG segmentation failed", exc_info=True)
            return [{"error": str(e)}]

    def healthcheck(self) -> bool:
        return self._available

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def last_latency_ms(self) -> float | None:
        return self._last_latency_ms


class BiRefNetSegmentationProvider:
    """Segmentation provider using BiRefNet (ZhengPeng7/BiRefNet) via custom code.

    Provides background removal and segmentation for item card images.
    BiRefNet won the 13-Jun-2026 Modal A10G seg bench (IoU 0.8555,
    pixel acc 0.9699, 0.432s/image, 20 synthetic product images).

    Uses the official custom code from the birefnet.py module, loaded
    as a package via importlib to handle relative imports correctly.

    Falls back gracefully when deps are missing.
    """

    name = "birefnet"
    model_id = "birefnet"
    parameter_count = 0.2
    license_note = "MIT"
    runtime_type = "transformers"
    supports_off_grid = True
    capabilities: set[str] = {"segmentation"}

    SAMPLE_SIZE = (1024, 1024)

    def __init__(
        self,
        model_name: str = "ZhengPeng7/BiRefNet",
        device: str = "auto",
    ):
        self._model_name = model_name
        self._device = device
        self._model = None
        self._transform = None
        self._BiRefNet = None
        self._available = False
        self._error: str | None = None
        self._last_latency_ms: float | None = None
        self._init()

    def _init(self) -> None:
        try:
            import torch  # noqa: F401
            from huggingface_hub import hf_hub_download  # noqa: F401
            import torchvision  # noqa: F401
            self._available = True
            self._error = None
            logger.info("BiRefNet provider initialised (model=%s)", self._model_name)
        except ImportError:
            self._error = (
                "torch/torchvision/huggingface_hub not installed. "
                "Run: uv pip install torch torchvision huggingface_hub"
            )
            self._available = False

    def load(self) -> None:
        if self._model is not None:
            return
        self._load_model()

    def _load_birefnet_module(self):
        """Load birefnet.py and BiRefNet_config.py from the repo as a package.

        BiRefNet uses relative imports in its custom code, so we need to
        create a synthetic package and load the modules in the right order.
        """
        import importlib.util
        from huggingface_hub import hf_hub_download

        birefnet_py = hf_hub_download("ZhengPeng7/BiRefNet", "birefnet.py")
        config_py = hf_hub_download("ZhengPeng7/BiRefNet", "BiRefNet_config.py")
        birefnet_dir = os.path.dirname(birefnet_py)

        pkg_name = "_birefnet_pkg_runtime"
        if pkg_name in sys.modules:
            return sys.modules[f"{pkg_name}.birefnet"].BiRefNet

        spec_cfg = importlib.util.spec_from_file_location(
            f"{pkg_name}.BiRefNet_config",
            config_py,
            submodule_search_locations=[birefnet_dir],
        )
        cfg_mod = importlib.util.module_from_spec(spec_cfg)
        sys.modules[f"{pkg_name}.BiRefNet_config"] = cfg_mod
        spec_cfg.loader.exec_module(cfg_mod)

        spec_bi = importlib.util.spec_from_file_location(
            f"{pkg_name}.birefnet",
            birefnet_py,
            submodule_search_locations=[birefnet_dir],
        )
        bi_mod = importlib.util.module_from_spec(spec_bi)
        sys.modules[f"{pkg_name}.birefnet"] = bi_mod
        spec_bi.loader.exec_module(bi_mod)
        return bi_mod.BiRefNet

    def _load_model(self) -> bool:
        if self._model is not None:
            return True
        try:
            import torch
            from torchvision import transforms

            BiRefNet = self._load_birefnet_module()
            self._BiRefNet = BiRefNet

            logger.info("Loading BiRefNet model %s ...", self._model_name)
            # Load in float32 to avoid deformable_im2col BFloat16 issue
            self._model = BiRefNet.from_pretrained(
                self._model_name,
                trust_remote_code=True,
                torch_dtype=torch.float32,
            )
            if self._device == "auto":
                if torch.cuda.is_available():
                    self._model = self._model.to("cuda")
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    self._model = self._model.to("mps")
            else:
                self._model = self._model.to(self._device)
            self._model.eval()

            self._transform = transforms.Compose([
                transforms.Resize(self.SAMPLE_SIZE),
                transforms.ToTensor(),
                transforms.Normalize([0.5] * 3, [0.5] * 3),
            ])
            logger.info("BiRefNet model loaded")
            return True
        except Exception as e:
            self._error = f"Failed to load BiRefNet model: {e}"
            logger.warning("BiRefNet model load failed", exc_info=True)
            return False

    def segment(self, image_path: str) -> list[dict[str, Any]]:
        """Segment an image and return mask data.

        Returns a list with a single foreground-background mask (BiRefNet
        outputs a single background-removal mask, similar to RMBG).
        """
        if not self._available:
            return [{"error": self._error or "BiRefNet not available"}]
        if not os.path.isfile(image_path):
            return [{"error": f"Image file not found: {image_path}"}]

        if self._model is None and not self._load_model():
            return [{"error": self._error or "Failed to load model"}]

        try:
            import torch
            from PIL import Image
            import numpy as np

            t0 = time.monotonic()

            image = Image.open(image_path).convert("RGB")
            w, h = image.size
            inp = self._transform(image).unsqueeze(0)
            if torch.cuda.is_available():
                inp = inp.to("cuda")
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                inp = inp.to("mps")

            with torch.no_grad():
                outputs = self._model(inp)
                # BiRefNet returns a tensor or single-element tuple; both index [0]
                first = outputs[0] if isinstance(outputs, (tuple, list)) else outputs
                mask = first.squeeze().sigmoid().float().cpu().numpy()

            elapsed = time.monotonic() - t0
            self._last_latency_ms = round(elapsed * 1000, 1)

            height, width = mask.shape
            fg_pixels = np.argwhere(mask > 0.5)
            if len(fg_pixels) > 0:
                y1, x1 = fg_pixels.min(axis=0)
                y2, x2 = fg_pixels.max(axis=0)
                bbox = [
                    round(x1 / width, 3),
                    round(y1 / height, 3),
                    round(x2 / width, 3),
                    round(y2 / height, 3),
                ]
            else:
                bbox = [0.0, 0.0, 1.0, 1.0]

            return [{
                "label": "foreground",
                "score": round(float(mask.mean()), 3),
                "mask": None,
                "bbox": bbox,
                "latency_ms": self._last_latency_ms,
            }]
        except Exception as e:
            logger.warning("BiRefNet segmentation failed", exc_info=True)
            return [{"error": str(e)}]

    def healthcheck(self) -> bool:
        return self._available

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def last_latency_ms(self) -> float | None:
        return self._last_latency_ms
