from __future__ import annotations

import os
import tempfile


def _build_host_app():
    fd, path = tempfile.mkstemp(suffix=".db", prefix="shopstack_frontend_")
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


def test_frontend_shell_is_the_root_surface():
    from fastapi.testclient import TestClient

    app, db, path, original_app_db, original_context_db = _build_host_app()
    try:
        client = TestClient(app)
        root = client.get("/")
        assert root.status_code == 200
        assert "text/html" in root.headers.get("content-type", "")
        body = root.text
        assert 'data-shell-root="true"' in body
        assert "story-title" in body
        assert "story-buy-pill" in body
        assert "story-use-pill" in body
        assert "story-cook-pill" in body
        assert "story-explore-pill" in body
        assert "What should I buy today?" in body
        assert "What should I use first?" in body
        assert "What can I cook from what I have?" in body
        assert "Show me the best deal and what is sold out." in body
        assert "/command/preview" in body
        assert "/command/execute" in body
        assert "/dashboard/today" in body
        assert "/auth/register" in body
        assert "/inventory/lots" in body
        assert "/shopping/active" in body
        assert "shopping-mark-purchased-btn" in body
        assert "/meta/runtime" in body
        assert "/account/privacy/retention-summary" in body
        assert "privacy-profile" in body
        assert "privacy-apply-profile-btn" in body
        assert "privacy-profile-summary" in body
        assert "privacy-update-btn" in body
        assert "privacy-purge-btn" in body
        assert "/corrections" in body
        assert "/account/undo" in body
        assert "/traces" in body
        assert "/search/global" in body
        assert "search-global-pill" in body
        assert "search-inventory-pill" in body
        assert "/intelligence/recurring" in body
        assert "recurring-window" in body
        assert "mealplan-days" in body
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
