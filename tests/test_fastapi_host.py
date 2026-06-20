"""Integration tests for the FastAPI host entrypoint."""
from __future__ import annotations

import os
import tempfile


def _build_host_app():
    fd, path = tempfile.mkstemp(suffix=".db", prefix="shopstack_fastapi_")
    os.close(fd)
    os.environ["SHOPSTACK_DB_PATH"] = path

    import app as app_module
    from shopstack import app_context
    from shopstack.persistence.database import Database
    from shopstack.server import build_fastapi_app

    original_app_db = app_module.db
    original_context_db = app_context.db
    db = Database(path)
    app_module.db = db
    app_context.db = db
    try:
        return build_fastapi_app(), db, path, original_app_db, original_context_db
    except Exception:
        db.close()
        app_module.db = original_app_db
        app_context.db = original_context_db
        raise


def test_fastapi_host_serves_api_and_ui():
    from fastapi.testclient import TestClient

    app, db, path, original_app_db, original_context_db = _build_host_app()
    try:
        client = TestClient(app)

        api = client.get("/api/v1/meta/whoami")
        assert api.status_code == 200
        payload = api.json()
        assert payload["app_name"] == "shopstack"

        health = client.get("/health/ui")
        assert health.status_code in (200, 503)

        manifest = client.get("/manifest.json")
        assert manifest.status_code == 200
        assert "manifest" in manifest.headers.get("content-type", "")

        root = client.get("/")
        assert root.status_code == 200
        assert "text/html" in root.headers.get("content-type", "")
        assert 'data-shell-root="true"' in root.text
        assert "/command/preview" in root.text
        assert "/inventory/lots" in root.text
        assert "/shopping/active" in root.text
        assert "shopping-mark-purchased-btn" in root.text
        assert "/meta/runtime" in root.text
        assert "/account/privacy/retention-summary" in root.text
        assert "privacy-profile" in root.text
        assert "privacy-apply-profile-btn" in root.text
        assert "privacy-profile-summary" in root.text
        assert "privacy-update-btn" in root.text
        assert "privacy-purge-btn" in root.text
        assert "/corrections" in root.text
        assert "/account/undo" in root.text
        assert "/traces" in root.text
        assert "/search/global" in root.text
        assert "search-global-pill" in root.text
        assert "search-inventory-pill" in root.text
        assert "/intelligence/recurring" in root.text
        assert "recurring-window" in root.text
        assert "mealplan-days" in root.text
    finally:
        db.close()
        import app as app_module
        from shopstack import app_context

        app_module.db = original_app_db
        app_context.db = original_context_db
        os.environ.pop("SHOPSTACK_DB_PATH", None)
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(path + suffix)
            except OSError:
                pass
