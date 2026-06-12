from __future__ import annotations

import logging
import os
import re
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

_ZBAR_PATH = "/opt/homebrew/lib/libzbar.dylib"


def _load_pyzbar():
    try:
        if os.path.exists(_ZBAR_PATH):
            import ctypes
            try:
                ctypes.cdll.LoadLibrary(_ZBAR_PATH)
            except Exception:
                logger.debug("Could not preload zbar shared library from %s", _ZBAR_PATH, exc_info=True)
        from pyzbar.pyzbar import decode as _pyzbar_decode, ZBarSymbol
        return _pyzbar_decode, ZBarSymbol
    except ImportError:
        return None, None


_pyzbar_decode, ZBarSymbol = _load_pyzbar()


def decode_barcode(image_path: str) -> list[dict[str, Any]]:
    if not os.path.exists(image_path):
        logger.debug("Barcode decode skipped: %s does not exist", image_path)
        return []

    if _pyzbar_decode is None:
        return _try_zbar_subprocess(image_path)

    from PIL import Image
    try:
        with Image.open(image_path) as img:
            results = _pyzbar_decode(img)
            return [
                {
                    "data": r.data.decode("utf-8", errors="replace"),
                    "type": str(r.type),
                    "rect": {
                        "x": r.rect.left,
                        "y": r.rect.top,
                        "w": r.rect.width,
                        "h": r.rect.height,
                    },
                }
                for r in results
            ]
    except Exception:
        logger.warning("pyzbar decode failed, falling back to subprocess", exc_info=True)
        return _try_zbar_subprocess(image_path)


def _try_zbar_subprocess(image_path: str) -> list[dict[str, Any]]:
    try:
        result = subprocess.run(
            ["zbarimg", "--raw", "-q", image_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = result.stdout.strip()
            code_type = _infer_barcode_type(data)
            return [{"data": data, "type": code_type, "source": "zbarimg"}]
    except FileNotFoundError:
        logger.info("zbarimg not available for barcode decoding")
    except Exception:
        logger.warning("zbarimg subprocess failed", exc_info=True)
    return []


def _infer_barcode_type(data: str) -> str:
    if re.match(r"^\d{12,13}$", data):
        return "EAN-13"
    if re.match(r"^\d{8}$", data):
        return "EAN-8"
    if re.match(r"^\d+$", data):
        return "CODE128"
    return "QRCODE"


def looks_like_product_code(code: str) -> bool:
    cleaned = code.strip()
    return bool(re.match(r"^\d{8,14}$", cleaned)) or cleaned.startswith("http")


def infer_product_from_code(code: str) -> dict[str, Any]:
    cleaned = code.strip()
    result: dict[str, Any] = {"code": cleaned}

    if cleaned.startswith("http"):
        result["type"] = "url"
        result["label"] = "Web link"
        return result

    digits = re.sub(r"\D", "", cleaned)
    if 8 <= len(digits) <= 14:
        result["type"] = "barcode"
        result["gtin"] = digits
        result["label"] = f"Product code {digits}"
        return result

    result["type"] = "unknown"
    result["label"] = cleaned
    return result
