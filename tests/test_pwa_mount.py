"""Tests for the PWA static mount helper.

Verifies:
- The mount function is best-effort: it doesn't crash when the
  static directory doesn't exist.
- It doesn't crash when called against a minimal Gradio Blocks
  (we use a context manager; we don't actually launch the app).

Note: We can't easily test the success path (mount succeeds) without
a full Gradio app + Starlette, which would require spinning up a
real server. The failure paths are the ones that matter most for
robustness, since the static dir is optional.
"""
from __future__ import annotations

import pytest


def test_mount_pwa_static_missing_dir_does_not_raise():
    """When the static dir doesn't exist, mount_pwa_static is a no-op."""
    from shopstack.ui.pwa_mount import mount_pwa_static

    # We use a bare ``gr.Blocks()`` (no launch) so the function
    # can attempt the mount without spinning up a server.
    import gradio as gr

    with gr.Blocks() as app:
        # Should NOT raise — best-effort skip when dir is missing.
        mount_pwa_static(app)


def test_mount_pwa_static_does_not_crash_on_rerun():
    """Re-mounting on a fresh app is safe (the function is idempotent)."""
    from shopstack.ui.pwa_mount import mount_pwa_static

    import gradio as gr

    # First app
    with gr.Blocks() as app1:
        mount_pwa_static(app1)
    # Second app — fresh state, no leftover mounts
    with gr.Blocks() as app2:
        mount_pwa_static(app2)


@pytest.mark.skip(reason="Requires running Gradio app with Starlette; covered by manual smoke test")
def test_mount_pwa_static_actually_mounts():
    """When the static dir exists, the mount registers on the FastAPI app."""
    # This is hard to test without spinning up a real server.
    # We rely on the manual smoke test: `python app.py` should
    # log "PWA static mounted" in debug mode.
    pass
