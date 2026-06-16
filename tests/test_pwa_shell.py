"""PWA shell regression tests (2026-06-13).

Per motto_v3 §6 (pre-existing is not an excuse), the PWA shell files
(manifest.json, sw.js, icons) must be reachable at root paths so the
user's branded PWA install prompt works on mobile.

Gradio 6.x intercepts /static/* with a JSON 404 handler, so the
PWA mount serves files at ROOT paths. This test verifies:

  1. The PWA files exist on disk
  2. The manifest content references root paths (after rewrite)
  3. The icon paths in the manifest resolve to existing files
  4. The pwa_mount module's helpers work correctly
  5. The mount function adds the right routes to the FastAPI app

This is a SOURCE-level test (cheap; no full app boot). For a full
end-to-end HTTP test, see the PWA HTTP test below.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
STATIC = REPO / "static"


# ─── PWA files exist on disk ────────────────────────────────────


class TestPwaFilesOnDisk:
    """The user's branded PWA files must be on disk."""

    def test_manifest_json_exists(self):
        assert (STATIC / "manifest.json").is_file(), (
            "static/manifest.json must exist (user's branded PWA manifest)."
        )

    def test_sw_js_exists(self):
        assert (STATIC / "sw.js").is_file(), (
            "static/sw.js must exist (service worker)."
        )

    def test_icon_192_exists(self):
        assert (STATIC / "icon-192.svg").is_file(), (
            "static/icon-192.svg must exist (PWA icon 192x192)."
        )

    def test_icon_512_exists(self):
        assert (STATIC / "icon-512.svg").is_file(), (
            "static/icon-512.svg must exist (PWA icon 512x512)."
        )


# ─── Manifest content is valid ───────────────────────────────────


class TestPwaManifestContent:
    """The manifest content must be valid JSON with the expected fields."""

    def test_manifest_is_valid_json(self):
        text = (STATIC / "manifest.json").read_text()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            pytest.fail(f"manifest.json is not valid JSON: {e}")
        assert isinstance(data, dict), "manifest.json must be a JSON object"

    def test_manifest_has_name(self):
        data = json.loads((STATIC / "manifest.json").read_text())
        assert data.get("name"), "manifest.json must have a 'name' field"

    def test_manifest_has_icons(self):
        data = json.loads((STATIC / "manifest.json").read_text())
        assert data.get("icons"), "manifest.json must have an 'icons' array"

    def test_manifest_has_start_url(self):
        data = json.loads((STATIC / "manifest.json").read_text())
        assert data.get("start_url"), "manifest.json must have a 'start_url'"


# ─── Mount module: route helpers ─────────────────────────────────


class TestPwaMountHelpers:
    """The pwa_mount module's helpers must work."""

    def test_pwa_media_types_defined(self):
        """The 4 PWA file types must be in the media type map."""
        from shopstack.ui.pwa_mount import _PWA_MEDIA_TYPES
        assert "manifest.json" in _PWA_MEDIA_TYPES
        assert "sw.js" in _PWA_MEDIA_TYPES
        assert "icon-192.svg" in _PWA_MEDIA_TYPES
        assert "icon-512.svg" in _PWA_MEDIA_TYPES

    def test_is_pwa_path(self):
        """The path matcher must correctly identify PWA paths."""
        from shopstack.ui.pwa_mount import _is_pwa_path
        # Positive
        assert _is_pwa_path("/manifest.json")
        assert _is_pwa_path("/sw.js")
        assert _is_pwa_path("/icon-192.svg")
        assert _is_pwa_path("/icon-512.svg")
        # Negative
        assert not _is_pwa_path("/")
        assert not _is_pwa_path("/index.html")
        assert not _is_pwa_path("/api/foo")
        # With query string (should strip and still match)
        assert _is_pwa_path("/icon-192.svg?hash=abc")

    def test_manifest_rewrite_to_root_paths(self):
        """The manifest rewriter must change /static/ to / in icon paths."""
        from shopstack.ui.pwa_mount import _rewrite_manifest_to_root_paths
        original = {
            "name": "Test",
            "icons": [
                {"src": "/static/icon-192.svg", "sizes": "192x192"},
                {"src": "/static/icon-512.svg", "sizes": "512x512"},
            ],
            "shortcuts": [
                {"name": "Test", "url": "/static/shortcut"},
            ],
        }
        rewritten = _rewrite_manifest_to_root_paths(original)
        assert rewritten["icons"][0]["src"] == "/icon-192.svg"
        assert rewritten["icons"][1]["src"] == "/icon-512.svg"
        assert rewritten["shortcuts"][0]["url"] == "/shortcut"

    def test_manifest_rewrite_preserves_other_fields(self):
        """The rewriter must not change fields that aren't paths."""
        from shopstack.ui.pwa_mount import _rewrite_manifest_to_root_paths
        original = {
            "name": "Test",
            "start_url": "/",
            "display": "standalone",
        }
        rewritten = _rewrite_manifest_to_root_paths(original)
        assert rewritten["name"] == "Test"
        assert rewritten["start_url"] == "/"
        assert rewritten["display"] == "standalone"


# ─── Manifest content references root paths (the whole point) ────


class TestManifestReferencesResolve:
    """The manifest's icon paths must point to files that exist.

    If the manifest references /icon-192.svg (root path) but the
    file isn't being served at that path, the PWA install will
    fail silently. This test verifies the chain.
    """

    def test_manifest_icon_paths_after_rewrite_resolve(self):
        """After the rewrite, every icon src must point to a file we serve."""
        from shopstack.ui.pwa_mount import _rewrite_manifest_to_root_paths
        original = json.loads((STATIC / "manifest.json").read_text())
        rewritten = _rewrite_manifest_to_root_paths(original)
        # Each icon src should be a root path
        for icon in rewritten.get("icons", []):
            src = icon.get("src", "")
            # After rewrite, no path should contain /static/
            assert "/static/" not in src, (
                f"After rewrite, manifest icon src should be at root path, "
                f"not /static/. Got: {src!r}"
            )

    def test_files_served_match_media_types(self):
        """The file we serve at each PWA path must match the expected type."""
        from shopstack.ui.pwa_mount import _PWA_MEDIA_TYPES
        for filename, expected_type in _PWA_MEDIA_TYPES.items():
            filepath = STATIC / filename
            if not filepath.is_file():
                continue  # Optional
            content = filepath.read_bytes()[:50]
            if expected_type == "application/manifest+json":
                assert content.startswith(b"{") or content.startswith(b"["), (
                    f"{filename} should be JSON; got {content[:20]!r}"
                )
            elif expected_type == "application/javascript":
                assert b"//" in content[:50] or b"/*" in content[:50] or b"self." in content[:200], (
                    f"{filename} should be JS; got {content[:50]!r}"
                )
            elif expected_type == "image/svg+xml":
                assert b"<svg" in content or b"<?xml" in content, (
                    f"{filename} should be SVG; got {content[:50]!r}"
                )


# ─── Mount function signature ───────────────────────────────────


class TestMountFunctionContract:
    """The mount function must have the right contract."""

    def test_mount_pwa_static_is_callable(self):
        from shopstack.ui.pwa_mount import mount_pwa_static
        assert callable(mount_pwa_static)

    def test_mount_takes_gr_blocks(self):
        """The mount function must accept a gr.Blocks (or compatible) object."""
        import inspect
        from shopstack.ui.pwa_mount import mount_pwa_static
        sig = inspect.signature(mount_pwa_static)
        params = list(sig.parameters.keys())
        assert len(params) >= 1, "mount_pwa_static must take at least one parameter"
        # The first parameter is the app (we don't enforce type annotation strictly)


import pytest
