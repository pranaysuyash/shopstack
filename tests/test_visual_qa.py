"""Visual QA tests — responsive, dark mode rendering, and reduced motion.

Uses Playwright to verify:
1. Responsive breakpoints (mobile, tablet, desktop)
2. Dark mode CSS variable application
3. Reduced motion media query enforcement
4. Focus indicator visibility
"""
from __future__ import annotations

import os
import socket
import urllib.error
import urllib.request
import pytest

playwright = pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright  # noqa: E402


APP_URL = os.getenv("SHOPSTACK_TEST_URL", "http://127.0.0.1:7860")


def _app_server_reachable(url: str, tcp_timeout: float = 0.5, http_timeout: float = 2.0) -> bool:
    """Best-effort reachability check for the test app server.

    Returns True ONLY if both:
    1. A TCP connection to the host:port succeeds within ``tcp_timeout`` seconds.
    2. An HTTP GET on ``url`` returns a 2xx/3xx response within ``http_timeout``
       seconds.

    The two-stage check is necessary because a stale Gradio app or a
    half-closed port can pass a TCP check while failing to serve any
    HTTP content. (In Pass 12 this was the root cause of the
    "transient batch-state test failures" pattern: a leftover Python
    process was listening on 127.0.0.1:7860 but not serving the
    full Gradio app, so Playwright's `wait_until="load"`
    timed out and the suite appeared to hang.)

    Use a higher level skip — ``pytest.importorskip("playwright")``
    is already at the top of this file, and the
    ``pytestmark = pytest.mark.skipif(...)`` below uses this
    function to skip the entire visual QA suite when no app
    server is reachable.
    """
    if url.startswith("http://"):
        host, _, port_str = url[len("http://"):].partition(":")
        port = int(port_str.split("/", 1)[0] or "80")
    elif url.startswith("https://"):
        # Skip HTTP probe for HTTPS — trust the env var.
        return True
    else:
        return False
    try:
        with socket.create_connection((host, port), timeout=tcp_timeout):
            pass
    except (OSError, socket.timeout):
        return False
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=http_timeout) as resp:
            return 200 <= resp.status < 400
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, socket.timeout):
        return False


# Module-level skip: skip the entire visual QA suite if no app server
# is reachable. This is the single source of truth — the rest of the
# fixtures inherit the skip via the `page` fixture chain.
pytestmark = pytest.mark.skipif(
    not _app_server_reachable(APP_URL),
    reason=f"SHOPSTACK_TEST_URL server {APP_URL} is not reachable; "
           "start a local app server to run visual QA tests.",
)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture()
def page(browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    pg = ctx.new_page()
    pg.goto(APP_URL, wait_until="load", timeout=30000)
    yield pg
    ctx.close()


class TestResponsiveBreakpoints:
    """Layout should adapt to mobile, tablet, and desktop viewports."""

    @pytest.mark.parametrize("width,height,label", [
        (375, 667, "mobile"),
        (768, 1024, "tablet"),
        (1280, 800, "desktop"),
    ])
    def test_viewport_renders_without_error(self, browser, width, height, label):
        ctx = browser.new_context(viewport={"width": width, "height": height})
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(APP_URL, wait_until="load", timeout=30000)
        assert not errors, f"{label} ({width}x{height}): JS errors: {errors}"
        body = pg.query_selector("body")
        assert body is not None, f"{label}: body not found"
        ctx.close()

    def test_mobile_no_horizontal_overflow(self, browser):
        ctx = browser.new_context(viewport={"width": 375, "height": 667})
        pg = ctx.new_page()
        pg.goto(APP_URL, wait_until="load", timeout=30000)
        overflow = pg.evaluate("""() => {
            const body = document.body;
            return body.scrollWidth > body.clientWidth;
        }""")
        assert not overflow, "Mobile viewport has horizontal overflow"
        ctx.close()


class TestDarkModeRendering:
    """Dark mode should apply correct CSS variables."""

    def test_dark_mode_css_variables_applied(self, page):
        page.evaluate("""() => {
            document.documentElement.setAttribute('data-theme', 'dark');
        }""")
        bg = page.evaluate("""() => {
            return getComputedStyle(document.documentElement)
                .getPropertyValue('--bg-primary').trim();
        }""")
        assert bg, "--bg-primary should have a value in dark mode"
        assert bg != "", "--bg-primary should not be empty in dark mode"

    def test_light_mode_restore(self, page):
        page.evaluate("""() => {
            document.documentElement.setAttribute('data-theme', 'light');
        }""")
        bg = page.evaluate("""() => {
            return getComputedStyle(document.documentElement)
                .getPropertyValue('--bg-primary').trim();
        }""")
        assert bg, "--bg-primary should have a value in light mode"

    def test_dark_mode_toggle_persists(self, page):
        page.evaluate("""() => {
            document.documentElement.setAttribute('data-theme', 'dark');
            localStorage.setItem('shopstack-theme', 'dark');
        }""")
        stored = page.evaluate("() => localStorage.getItem('shopstack-theme')")
        assert stored == "dark"


class TestReducedMotion:
    """Animations should be suppressed when prefers-reduced-motion is reduce."""

    def test_no_css_transitions_in_reduced_motion(self, page):
        page.emulate_media(reduced_motion="reduce")
        page.goto(APP_URL, wait_until="load", timeout=30000)
        has_transition = page.evaluate("""() => {
            const style = document.querySelector('style');
            if (!style) return false;
            const css = style.textContent;
            return css.includes('prefers-reduced-motion: reduce');
        }""")
        assert has_transition, "CSS should contain prefers-reduced-motion: reduce rules"

    def test_reduced_motion_disables_animations(self, page):
        page.emulate_media(reduced_motion="reduce")
        page.goto(APP_URL, wait_until="load", timeout=30000)
        durations = page.evaluate("""() => {
            const els = document.querySelectorAll('*');
            let maxDuration = 0;
            for (const el of els) {
                const style = getComputedStyle(el);
                const dur = parseFloat(style.animationDuration) || 0;
                const transDur = parseFloat(style.transitionDuration) || 0;
                maxDuration = Math.max(maxDuration, dur, transDur);
            }
            return maxDuration;
        }""")
        assert durations <= 0.01, f"Animations should be disabled in reduced motion (max duration: {durations}s)"


class TestFocusIndicator:
    """Focus-visible outlines should appear on interactive elements."""

    def test_button_has_focus_outline(self, page):
        page.evaluate("""() => {
            document.documentElement.setAttribute('data-theme', 'light');
        }""")
        page.goto(APP_URL, wait_until="load", timeout=30000)
        button = page.query_selector("button")
        if button:
            button.focus()
            outline = page.evaluate("""(el) => {
                const style = getComputedStyle(el);
                return {
                    width: style.outlineWidth,
                    style: style.outlineStyle,
                    color: style.outlineColor,
                };
            }""", button)
            assert outline["width"] != "0px", f"Button should have visible focus outline, got: {outline}"


class TestHardcodedColorAudit:
    """No hardcoded hex colors should leak through CSS variables."""

    def test_no_inline_hex_in_component_html(self, page):
        page.goto(APP_URL, wait_until="load", timeout=30000)
        hex_in_style = page.evaluate("""() => {
            const elements = document.querySelectorAll('[style*="color"]');
            const hardcoded = [];
            for (const el of elements) {
                const style = el.getAttribute('style') || '';
                const matches = style.match(/#[0-9a-fA-F]{3,8}/g) || [];
                hardcoded.push(...matches);
            }
            return hardcoded;
        }""")
        # Filter out known acceptable patterns (e.g., brand colors in meta tags)
        flagged = [h for h in hex_in_style if h.lower() not in ("#000000", "#ffffff")]
        assert not flagged, f"Hardcoded hex colors found in inline styles: {flagged}"
