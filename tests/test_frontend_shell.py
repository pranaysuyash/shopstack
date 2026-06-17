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
        assert "/api/v1/command/preview" in body
        assert "/api/v1/command/execute" in body
        assert "/api/v1/dashboard/today" in body
        assert "/api/v1/auth/register" in body
        assert "/api/v1/inventory/lots" in body
        assert "/api/v1/shopping/active" in body
        assert "/search/global" in body
        assert "/intelligence/recurring" in body
        assert "/gradio" in body

        gradio = client.get("/gradio")
        assert gradio.status_code == 200
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
