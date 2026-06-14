#!/usr/bin/env python3
"""Pre-download BiRefNet segmentation model weights to HuggingFace cache.

Run once to avoid the 10-30s download on the first Shelf Scan call:

    uv run python scripts/download_birefnet.py

After this, ``BiRefNetSegmentationProvider``'s first ``segment()`` call
will find weights already cached and load in <2s.
"""

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("download_birefnet")


def main() -> None:
    model_name = "ZhengPeng7/BiRefNet"
    logger.info("Downloading BiRefNet model weights from %s ...", model_name)
    logger.info("This may take 10-30s depending on bandwidth (~200MB).")

    try:
        from huggingface_hub import snapshot_download, hf_hub_download

        # Download all model repo files
        path = snapshot_download(model_name)
        logger.info("Model weights cached at: %s", path)

        # Also explicitly cache the custom-code files
        birefnet_py = hf_hub_download(model_name, "birefnet.py")
        config_py = hf_hub_download(model_name, "BiRefNet_config.py")
        logger.info("Custom code cached: %s", birefnet_py)
        logger.info("Custom code cached: %s", config_py)

        logger.info("")
        logger.info("✅ BiRefNet model weights pre-downloaded successfully.")
        logger.info("The first segment() call will now load from cache in <2s.")
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
