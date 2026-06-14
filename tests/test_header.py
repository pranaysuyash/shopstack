"""Tests for the header state and rendering module.

Verifies:
- `runtime_label()` returns the right label for each provider state
- `model_download_status()` returns empty when the model is cached,
  a download hint when it's not
- `header_html()` and `header_script()` return well-formed strings
- `header_block()` combines them correctly
- `_pwa_block()` includes the manifest link and service worker registration
"""
from __future__ import annotations

import os


def test_runtime_label_default_is_local_mock():
    """With mock providers (the default), the label is 'Local mock mode'."""
    # No env var changes; use whatever the singleton has
    from shopstack.ui.header import runtime_label
    label = runtime_label()
    # The label is one of the 4 valid options
    assert label in {"Local mock mode", "Local runtime", "Cloud runtime", "Off-grid mock mode"}


def test_runtime_label_handles_provider_exception():
    """If providers.get_runtime_diagnostics() throws, fall back to 'Local runtime'."""
    from unittest.mock import patch
    from shopstack.ui import header

    with patch("shopstack.ui.header.providers") as mock_providers:
        mock_providers.get_runtime_diagnostics.side_effect = RuntimeError("boom")
        assert header.runtime_label() == "Local runtime"


def test_model_download_status_no_mlx_model():
    """When local_mlx_model is empty, no download status is shown."""
    from unittest.mock import patch
    from shopstack.ui import header

    with patch("shopstack.ui.header.settings") as mock_settings:
        mock_settings.local_mlx_model = ""
        assert header.model_download_status() == ""


def test_model_download_status_uncached_returns_html(tmp_path, monkeypatch):
    """When the MLX model isn't cached, an HTML snippet is returned."""
    from shopstack.ui import header

    monkeypatch.setattr(header.settings, "local_mlx_model", "test-org/test-model")
    # Point HF_HOME to an empty tempdir so the cache lookup fails
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    result = header.model_download_status()
    assert "download pending" in result
    assert "test-model" in result


def test_model_download_status_cached_returns_empty(tmp_path, monkeypatch):
    """When the model is cached (snapshots dir with .safetensors), no hint."""
    from shopstack.ui import header

    # Set up a fake cache: hf_cache / hub / models--X / snapshots / <sha> / model.safetensors
    hf_cache = tmp_path
    model_dir = hf_cache / "hub" / "models--test-org--test-model"
    snapshots = model_dir / "snapshots" / "abc123"
    snapshots.mkdir(parents=True)
    (snapshots / "model.safetensors").write_bytes(b"fake")

    monkeypatch.setattr(header.settings, "local_mlx_model", "test-org/test-model")
    monkeypatch.setenv("HF_HOME", str(hf_cache))
    result = header.model_download_status()
    assert result == ""


def test_header_html_includes_brand_title():
    """The header HTML must include the brand title and a theme toggle."""
    from shopstack.ui.header import header_html
    html = header_html("MyApp", "My subtitle")
    assert "MyApp" in html
    assert "My subtitle" in html
    assert "toggleTheme" in html
    assert "🌓" in html  # theme toggle emoji


def test_header_html_escapes_user_input():
    """Brand title and subtitle should be HTML-escaped to prevent XSS."""
    from shopstack.ui.header import header_html
    html = header_html("<script>x</script>", "Plain text")
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


def test_header_script_includes_theme_persistence():
    """The script must include the localStorage theme save/load logic."""
    from shopstack.ui.header import header_script
    script = header_script()
    assert "localStorage" in script
    assert "shopstack-theme" in script
    assert "toggleTheme" in script


def test_header_script_includes_keyboard_shortcuts():
    """The script must include j/k/ArrowRight/ArrowLeft tab navigation."""
    from shopstack.ui.header import header_script
    script = header_script()
    assert "ArrowRight" in script
    assert "ArrowLeft" in script
    assert "'j'" in script or '"j"' in script
    assert "'k'" in script or '"k"' in script


def test_header_block_combines_html_and_script():
    """header_block returns HTML + script as a single string.

    The PWA manifest link + service worker registration are NOT part of
    header_block — they live in ``pwa_head_html()`` and are injected via
    ``app.launch(head=...)`` instead, because <script> tags rendered via
    gr.HTML's innerHTML never execute.
    """
    from shopstack.ui.header import header_block
    block = header_block("MyApp", "My subtitle")
    assert "MyApp" in block
    assert "toggleTheme" in block
    assert "localStorage" in block


def test_pwa_head_html_includes_manifest_and_sw():
    """pwa_head_html includes the manifest link, theme color, and SW registration
    at root paths (matching where mount_pwa_static actually serves them)."""
    from shopstack.ui.header import pwa_head_html
    block = pwa_head_html()
    assert 'rel="manifest"' in block
    assert 'href="/manifest.json"' in block
    assert 'name="theme-color"' in block
    assert "serviceWorker" in block
    assert "register('/sw.js'" in block
    assert "/static/manifest.json" not in block
    assert "/static/sw.js" not in block
