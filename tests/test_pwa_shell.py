"""Tests for the Phase 4 #5 PWA shell (manifest + service worker + icons).

The PWA shell is small — a manifest, a service worker JS, two SVG
icons. These tests verify:
- All four files exist and are non-empty.
- The manifest JSON is valid and has the required fields.
- The service worker JS is syntactically valid JavaScript.
- The icons are valid SVG.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


def _read(name: str) -> str:
    p = STATIC_DIR / name
    assert p.is_file(), f"{p} does not exist"
    return p.read_text(encoding="utf-8")


class TestPWAShell:
    def test_manifest_exists(self):
        assert (STATIC_DIR / "manifest.json").is_file()

    def test_manifest_is_valid_json(self):
        text = _read("manifest.json")
        data = json.loads(text)
        assert isinstance(data, dict)

    def test_manifest_has_required_fields(self):
        data = json.loads(_read("manifest.json"))
        for field in ("name", "short_name", "start_url", "display", "icons"):
            assert field in data, f"manifest.json missing required field: {field}"
        # Must be a PWA manifest — at least one icon
        assert isinstance(data["icons"], list) and len(data["icons"]) >= 1

    def test_manifest_icons_reference_real_files(self):
        data = json.loads(_read("manifest.json"))
        for icon in data["icons"]:
            src = icon.get("src", "")
            # Strip leading "/" since we serve from /static
            rel = src.lstrip("/")
            if rel.startswith("static/"):
                rel = rel[len("static/"):]
            assert (STATIC_DIR / rel).is_file(), f"icon src {src} → {rel} not found"

    def test_service_worker_exists(self):
        assert (STATIC_DIR / "sw.js").is_file()

    def test_service_worker_is_syntactically_valid_js(self):
        """Smoke test: the sw.js should not have obvious syntax errors.
        We can't execute browser JS in Python, but we can check that
        the file is non-empty, has install/activate/fetch handlers,
        and doesn't have unmatched braces.
        """
        text = _read("sw.js")
        assert "addEventListener" in text
        assert "install" in text
        assert "activate" in text
        assert "fetch" in text
        # Brace balance (ignoring braces inside strings, which we don't
        # have in this file)
        assert text.count("{") == text.count("}"), "unbalanced braces in sw.js"

    def test_icon_192_is_valid_svg(self):
        text = _read("icon-192.svg")
        # Should be parseable XML starting with <svg
        assert text.lstrip().startswith("<?xml") or text.lstrip().startswith("<svg")
        # Parse it
        root = ET.fromstring(text)
        tag = root.tag.split("}")[-1]  # strip namespace
        assert tag == "svg"

    def test_icon_512_is_valid_svg(self):
        text = _read("icon-512.svg")
        root = ET.fromstring(text)
        tag = root.tag.split("}")[-1]
        assert tag == "svg"

    def test_app_py_injects_manifest_link(self):
        """The app.py header should reference /static/manifest.json
        so the browser picks it up."""
        # The PWA manifest link is now injected via shopstack/ui/header.py
        # (Phase 4 refactor moved it out of app.py into the shared header block
        # so the same HTML is used for tests, brand blocks, and app composition).
        header_path = Path(__file__).resolve().parents[1] / "shopstack" / "ui" / "header.py"
        header_content = header_path.read_text(encoding="utf-8")
        assert "/static/manifest.json" in header_content, "header.py should reference the manifest"
        assert "/static/sw.js" in header_content, "header.py should reference the service worker"
        # The PWA mount wiring still lives in app.py
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        app_content = app_path.read_text(encoding="utf-8")
        assert "StaticFiles" in app_content or "add_route" in app_content or "mount" in app_content
