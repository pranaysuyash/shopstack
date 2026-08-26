"""Native web-app contract tests.

These tests exercise the supported FastAPI surface directly. They intentionally
do not import, mock, or require the retired Gradio UI.
"""
from __future__ import annotations

import subprocess
import sys

from fastapi.testclient import TestClient


def test_native_app_serves_web_api_and_pwa(app):
    from shopstack.server import build_fastapi_app

    built = build_fastapi_app()
    paths = {getattr(route, "path", "") for route in built.routes}
    assert "/" in paths
    assert "/api/v1/meta/whoami" in paths
    assert "/manifest.json" in paths
    assert "/gradio" not in paths

    client = TestClient(built)
    root = client.get("/")
    assert root.status_code == 200
    assert 'data-shell-root="true"' in root.text
    assert "text/html" in root.headers.get("content-type", "")

    manifest = client.get("/manifest.json")
    assert manifest.status_code == 200
    assert manifest.headers["content-type"].startswith("application/manifest+json")

    health = client.get("/health/ui")
    assert health.status_code in {200, 503}
    assert "web_app" in health.json()["checks"]


def test_native_entrypoint_import_graph_is_gradio_free():
    script = """
import builtins
real_import = builtins.__import__
def blocked(name, *args, **kwargs):
    if name == 'gradio' or name.startswith('gradio.'):
        raise AssertionError(f'canonical app imported gradio: {name}')
    return real_import(name, *args, **kwargs)
builtins.__import__ = blocked
from shopstack.server import build_fastapi_app
app = build_fastapi_app()
assert not any(getattr(route, 'path', '') == '/gradio' for route in app.routes)
print(len(app.routes))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )
    assert int(result.stdout.strip().splitlines()[-1]) >= 60
