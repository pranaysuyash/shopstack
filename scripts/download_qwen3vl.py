#!/usr/bin/env python3
"""Pre-download Qwen3-VL vision model weights to HuggingFace cache.

Run once to avoid the 30-120s download on the first ``understand()`` call:

    uv run python scripts/download_qwen3vl.py

After this, ``Qwen3VLProvider``'s first ``understand()`` call will find
weights already cached and load in <5s. The provider also kicks off
this same pre-download in a background thread on construction (Pass 14
§1.4 — same pattern as BiRefNet §1.3); this script is a manual
fallback / opt-in for users who want to pre-cache without starting
the app.

The model is ~16GB with 4-bit quantization, ~32GB in bf16. The
download is large; on a 50 Mbps connection it takes ~50-90 minutes
for the full bf16 weights. With HF's chunked transfer + 4-bit, the
runtime model size is ~8GB.
"""

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("download_qwen3vl")


def main() -> None:
    model_name = "Qwen/Qwen3-VL-8B-Instruct"
    logger.info("Downloading Qwen3-VL model weights from %s ...", model_name)
    logger.info(
        "This is a large download (~8-16GB depending on quantization); "
        "may take 10-90 minutes on a typical broadband connection."
    )

    try:
        from huggingface_hub import snapshot_download

        # Download all model repo files to HF cache
        path = snapshot_download(model_name)
        logger.info("Model weights cached at: %s", path)

        logger.info("")
        logger.info("Qwen3-VL model weights pre-downloaded successfully.")
        logger.info("The first understand() call will now load from cache in <5s.")
    except ImportError:
        logger.error(
            "Missing huggingface_hub. Install with: uv pip install huggingface_hub"
        )
        sys.exit(1)
    except Exception as e:
        logger.error("Download failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
