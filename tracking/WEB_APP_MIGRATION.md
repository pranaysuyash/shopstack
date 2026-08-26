# ShopStack web and mobile application boundary

ShopStack has one supported product backend and two supported clients:

- `shopstack/server.py` builds the native FastAPI host.
- `shopstack/ui/frontend_shell.py` serves the browser application at `/`.
- `shopstack-mobile/` is the Expo client for iOS, Android, and Expo web.
- Both clients use the same `/api/v1/*` contract.

The Gradio UI is retired from the product boundary. It is not installed by
the base package, is not mounted at `/gradio`, and is not used by the Docker,
CI, or application entrypoint paths. The old component builders and their
tests remain in the repository as historical recovery material only. They are
not part of the native test gate and must not be imported by new code.

## Invariants

1. `python app.py` and `python run.py` start Uvicorn with the FastAPI app.
2. `/` is the browser shell and `/api/v1/*` is the shared transport contract.
3. PWA assets are served directly at `/manifest.json`, `/sw.js`, and the icon
   paths, without a UI framework catch-all.
4. The base Python install contains FastAPI and Uvicorn, but not Gradio.
5. Native web tests must prove the route surface and a Gradio-free canonical
   import graph.
6. The mobile app remains a separate client. It must not import Python code or
   reach into the database directly.

## Recovery boundary

Legacy Gradio code is deliberately retained until the mobile and browser
surfaces have feature parity and the recovery review is complete. Retention
does not make it supported: no new feature should be implemented there, and
no deployment or CI path may reintroduce it as a dependency. The API and
service layers are the canonical places to recover valuable behavior.

## Verification commands

```bash
uv run python -c "from shopstack.server import build_fastapi_app; print(build_fastapi_app().title)"
uv run pytest tests/test_native_web_app.py -q
cd shopstack-mobile && npm run typecheck
```
