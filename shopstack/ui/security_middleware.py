"""Security middleware for the ShopStack native web app.

Extracted from ``app.py`` (Pass 26, 2026-06-17) to keep the
composition root under the 300-line cap asserted by
``test_household_wiring.py::TestAppLineCount::test_app_under_300_lines``.

Contains:

* :class:`PermissionsPolicyMiddleware` — adds a restrictive
  ``Permissions-Policy`` header to all responses.
* :func:`install_permissions_policy_middleware` — idempotent
  installer for a FastAPI application.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class PermissionsPolicyMiddleware(BaseHTTPMiddleware):
    """Add a restrictive Permissions-Policy header to all responses.

    The policy restricts access to sensitive browser APIs by default.
    Only features needed by the app should be explicitly allowed.
    """

    # Valid Permissions-Policy features (per W3C spec)
    # We disable all by default. Enable only what the app actually uses.
    PERMISSIONS_POLICY = (
        "accelerometer=(), "
        "ambient-light-sensor=(), "
        "autoplay=(), "
        "battery=(), "
        "camera=(), "
        "display-capture=(), "
        "document-domain=(), "
        "encrypted-media=(), "
        "fullscreen=(), "
        "gamepad=(), "
        "geolocation=(), "
        "gyroscope=(), "
        "hid=(), "
        "identity-credentials-get=(), "
        "idle-detection=(), "
        "keyboard-map=(), "
        "local-fonts=(), "
        "magnetometer=(), "
        "microphone=(), "
        "midi=(), "
        "otp-credentials=(), "
        "payment=(), "
        "picture-in-picture=(), "
        "publickey-credentials-create=(), "
        "publickey-credentials-get=(), "
        "screen-wake-lock=(), "
        "serial=(), "
        "speaker-selection=(), "
        "sync-xhr=(), "
        "usb=(), "
        "web-share=(), "
        "window-management=(), "
        "xr-spatial-tracking=()"
    )

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Permissions-Policy"] = self.PERMISSIONS_POLICY
        return response


def install_permissions_policy_middleware(app) -> None:  # noqa: ANN001
    """Install the Permissions-Policy middleware on a FastAPI app.

    Idempotent: if the middleware is already installed (e.g. because a previous
    test in the same process already called this), the ``RuntimeError`` is
    silently caught. In production, ``build_app()`` is called once so the
    middleware is always installed correctly on the first call.
    """
    try:
        app.add_middleware(PermissionsPolicyMiddleware)
    except RuntimeError:
        # ``Cannot add middleware after an application has started`` —
        # occurs when two or more app-launch test files run in the same
        # process. The middleware is already installed by the first test;
        # the second call is a no-op.
        pass


__all__ = [
    "PermissionsPolicyMiddleware",
    "install_permissions_policy_middleware",
]
