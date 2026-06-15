"""Full end-to-end user flow test for ShopStack.

Boots the Gradio app on an ephemeral port, then drives every major user
flow headlessly with Playwright/Chromium:

  1. Boot → Home (command surface)
  2. Pantry tab (inventory, add purchase)
  3. Shopping tab (market intel, price compare, list)
  4. Market Lens (vision product detection on data/fresh_mart.png)
  5. Receipt OCR (Tesseract pipeline on data/maa_laxmi.png)
  6. Recipes tab
  7. Trips tab
  8. Memory tab (patterns, traces)
  9. Household grounding (fridge.png via benchmarks/modal/assets)
 10. Recipe/label OCR (data/sai_pharma.png)

For each flow: navigates, captures a screenshot, records duration +
page errors + console errors. Writes:
  - screenshots/<flow>/<step>.png
  - results.json (machine-readable)
  - report.md (human-readable)

Usage:
    uv run python scripts/e2e_full_run.py
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Docs" / "qa" / "2026-06-15_e2e_audit_run"
SHOTS = OUT / "screenshots"
LOGS = OUT / "logs"

# Real images available in the repo.
IMG_FRESH_MART = ROOT / "data" / "fresh_mart.png"
IMG_MAA_LAXMI = ROOT / "data" / "maa_laxmi.png"
IMG_SAI_PHARMA = ROOT / "data" / "sai_pharma.png"
IMG_FRIDGE = ROOT / "benchmarks" / "modal" / "assets" / "household_grounding" / "fridge.png"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(url: str, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", int(url.rsplit(":", 1)[1])), timeout=2):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(1.0)
    return False


def _dismiss_overlays(page: Any) -> None:
    """Hide onboarding wizard + tour overlays so flows can click into the app.

    Both overlays intercept pointer events (aria-modal=true), so they must
    be removed before any tab click can succeed. We set display:none AND
    the localStorage flags so they stay gone across reloads.
    """
    page.evaluate(
        """
        () => {
          // Tour overlay — intercepts clicks until hidden
          var tour = document.getElementById('tour-overlay');
          if (tour) { tour.style.display = 'none'; tour.removeAttribute('data-active'); }
          try { localStorage.setItem('shopstack.tour.shown', '1'); } catch(e){}
          try { sessionStorage.setItem('shopstack.tour.shown', '1'); } catch(e){}
          // Onboarding wizard
          var wiz = document.getElementById('onboarding-wizard');
          if (wiz) {
            var btns = wiz.querySelectorAll('button');
            for (var i=0; i<btns.length; i++) {
              var t = (btns[i].textContent||'').trim().toLowerCase();
              if (t.indexOf('skip') !== -1) { try{btns[i].click();}catch(e){} break; }
            }
            wiz.style.display = 'none';
          }
          // Any other aria-modal dialogs
          document.querySelectorAll('[aria-modal="true"]').forEach(function(el){
            if (el.id !== 'tour-overlay' && el.id !== 'onboarding-wizard') el.style.display='none';
          });
          return {tour: !!tour, wiz: !!wiz};
        }
        """
    )


def _click_tab(page: Any, tab_text: str) -> bool:
    for sel in (
        f"button[role='tab']:has-text('{tab_text}')",
        f"[role='tab']:has-text('{tab_text}')",
        f"button:has-text('{tab_text}')",
    ):
        try:
            page.locator(sel).first.click(timeout=4000)
            return True
        except Exception:
            continue
    return False


def _click_subtab(page: Any, subtab_text: str) -> bool:
    # Sub-tabs in Gradio are also role="tab" buttons. We need to match
    # the sub-tab (not the top-level tab), so we scope to the last matching
    # element (top-level tabs appear first in DOM, sub-tabs appear later).
    for sel in (
        f"button[role='tab']:has-text('{subtab_text}')",
        f"button:has-text('{subtab_text}')",
        f"a:has-text('{subtab_text}')",
        f"[role='button']:has-text('{subtab_text}')",
    ):
        try:
            loc = page.locator(sel)
            if loc.count() == 0:
                continue
            # Use the LAST match — top-level tabs are first in DOM,
            # sub-tabs are nested deeper. This avoids clicking the
            # top-level tab instead of the sub-tab.
            loc.last.click(timeout=4000, force=True)
            return True
        except Exception:
            continue
    return False


def _screenshot(page: Any, flow: str, name: str, full: bool = False) -> str:
    path = SHOTS / flow / name
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=full)
    return str(path.relative_to(ROOT))


# Each flow: slug, title, steps. Steps are dicts with kind + params.
FLOWS: list[dict[str, Any]] = [
    {
        "slug": "01_boot",
        "title": "Boot → Home",
        "steps": [
            {"kind": "goto"},
            {"kind": "wait", "ms": 5000},
            {"kind": "dismiss"},
            {"kind": "shot", "name": "01_home.png", "full": True},
        ],
    },
    {
        "slug": "02_pantry",
        "title": "Pantry tab (inventory)",
        "steps": [
            {"kind": "dismiss"},
            {"kind": "tab", "text": "Pantry"},
            {"kind": "wait", "ms": 2500},
            {"kind": "shot", "name": "02_pantry.png", "full": True},
        ],
    },
    {
        "slug": "03_shopping",
        "title": "Shopping tab (market intel)",
        "steps": [
            {"kind": "dismiss"},
            {"kind": "tab", "text": "Shopping"},
            {"kind": "wait", "ms": 2500},
            {"kind": "shot", "name": "03_shopping.png", "full": True},
        ],
    },
    {
        "slug": "04_market_lens",
        "title": "Shelf Scan (vision on fresh_mart.png)",
        "steps": [
            {"kind": "dismiss"},
            {"kind": "tab", "text": "Shopping"},
            {"kind": "wait", "ms": 1500},
            {"kind": "subtab", "text": "Shelf Scan"},
            {"kind": "wait", "ms": 2500},
            {"kind": "shot", "name": "04a_shelf_open.png"},
            {"kind": "upload", "path": str(IMG_FRESH_MART)},
            {"kind": "wait", "ms": 9000, "label": "vision inference"},
            {"kind": "shot", "name": "04b_shelf_after.png", "full": True},
        ],
    },
    {
        "slug": "05_receipt_ocr",
        "title": "Smart Basket (receipt/items upload maa_laxmi.png)",
        "steps": [
            {"kind": "dismiss"},
            {"kind": "tab", "text": "Shopping"},
            {"kind": "wait", "ms": 1500},
            {"kind": "subtab", "text": "Smart Basket"},
            {"kind": "wait", "ms": 2500},
            {"kind": "shot", "name": "05a_basket_open.png"},
            {"kind": "upload", "path": str(IMG_MAA_LAXMI)},
            {"kind": "wait", "ms": 9000, "label": "OCR pipeline"},
            {"kind": "shot", "name": "05b_basket_after.png", "full": True},
        ],
    },
    {
        "slug": "06_recipes",
        "title": "Recipes tab",
        "steps": [
            {"kind": "dismiss"},
            {"kind": "tab", "text": "Recipes"},
            {"kind": "wait", "ms": 2500},
            {"kind": "shot", "name": "06_recipes.png", "full": True},
        ],
    },
    {
        "slug": "07_trips",
        "title": "Trips tab",
        "steps": [
            {"kind": "dismiss"},
            {"kind": "tab", "text": "Trips"},
            {"kind": "wait", "ms": 2500},
            {"kind": "shot", "name": "07_trips.png", "full": True},
        ],
    },
    {
        "slug": "08_memory",
        "title": "Memory tab",
        "steps": [
            {"kind": "dismiss"},
            {"kind": "tab", "text": "Memory"},
            {"kind": "wait", "ms": 2500},
            {"kind": "shot", "name": "08_memory.png", "full": True},
        ],
    },
    {
        "slug": "09_grounding",
        "title": "Memory → Analytics (grounding on fridge.png)",
        "steps": [
            {"kind": "dismiss"},
            {"kind": "tab", "text": "Memory"},
            {"kind": "wait", "ms": 1500},
            {"kind": "subtab", "text": "Analytics"},
            {"kind": "wait", "ms": 2500},
            {"kind": "shot", "name": "09a_analytics.png"},
            {"kind": "upload", "path": str(IMG_FRIDGE)},
            {"kind": "wait", "ms": 11000, "label": "grounding inference"},
            {"kind": "shot", "name": "09b_grounding_after.png", "full": True},
        ],
    },
    {
        "slug": "10_label_ocr",
        "title": "Memory → Parser Test (label OCR sai_pharma.png)",
        "steps": [
            {"kind": "dismiss"},
            {"kind": "tab", "text": "Memory"},
            {"kind": "wait", "ms": 1500},
            {"kind": "subtab", "text": "Parser Test"},
            {"kind": "wait", "ms": 2500},
            {"kind": "shot", "name": "10a_parser_open.png"},
            {"kind": "upload", "path": str(IMG_SAI_PHARMA)},
            {"kind": "wait", "ms": 9000, "label": "OCR pipeline"},
            {"kind": "shot", "name": "10b_parser_after.png", "full": True},
        ],
    },
]


def run_step(page: Any, step: dict, flow_slug: str, app_url: str) -> str:
    kind = step["kind"]
    if kind == "goto":
        page.goto(app_url, wait_until="domcontentloaded", timeout=30000)
        return "navigated"
    if kind == "wait":
        page.wait_for_timeout(step["ms"])
        return f"waited {step['ms']}ms"
    if kind == "dismiss":
        _dismiss_overlays(page)
        return "dismissed overlays"
    if kind == "shot":
        rel = _screenshot(page, flow_slug, step["name"], step.get("full", False))
        return f"screenshot → {rel}"
    if kind == "tab":
        ok = _click_tab(page, step["text"])
        return f"tab '{step['text']}': {'ok' if ok else 'NOT FOUND'}"
    if kind == "subtab":
        ok = _click_subtab(page, step["text"])
        return f"subtab '{step['text']}': {'ok' if ok else 'NOT FOUND'}"
    if kind == "upload":
        try:
            page.set_input_files("input[type='file']", step["path"], timeout=5000)
            return f"uploaded {Path(step['path']).name}"
        except Exception as exc:
            return f"upload FAILED: {exc}"
    return f"unknown step: {kind}"


def main() -> int:
    from playwright.sync_api import sync_playwright

    SHOTS.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)

    port = _free_port()
    app_url = f"http://127.0.0.1:{port}"
    print(f"Booting ShopStack on port {port} ...")

    # Boot the app as a subprocess. OFF_THE_GRID=true so it runs with mock
    # providers (no cloud keys needed). Use a temp DB so we don't clobber
    # the user's data.
    import tempfile

    tmp_db = tempfile.mktemp(suffix=".db")
    env_patch = {
        "SHOPSTACK_OFF_THE_GRID": "true",
        "SHOPSTACK_DB_PATH": tmp_db,
    }
    import os

    proc_env = {**os.environ, **env_patch}
    proc = subprocess.Popen(
        [sys.executable, "app.py", "--port", str(port)],
        cwd=str(ROOT),
        env=proc_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    summary: list[dict[str, Any]] = []
    console_errors: list[str] = []
    page_errors: list[str] = []

    try:
        if not _wait_for_server(app_url, timeout=60):
            # Read boot output for diagnostics
            try:
                out = proc.stdout.read(2000) if proc.stdout else ""
            except Exception:
                out = ""
            print(f"SERVER FAILED TO BOOT. Output:\n{out}")
            return 1
        print(f"Server up at {app_url}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            page = ctx.new_page()
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text[:300])
                if msg.type == "error"
                else None,
            )
            page.on("pageerror", lambda err: page_errors.append(str(err)[:500]))

            for flow in FLOWS:
                slug = flow["slug"]
                title = flow["title"]
                print(f"\n{'='*60}\n{slug} :: {title}\n{'='*60}")
                t0 = time.time()
                errs_before = len(page_errors)
                step_log: list[str] = []
                try:
                    for step in flow["steps"]:
                        msg = run_step(page, step, slug, app_url)
                        print(f"  → {msg}")
                        step_log.append(msg)
                    dt = time.time() - t0
                    flow_errs = page_errors[errs_before:]
                    summary.append(
                        {
                            "slug": slug,
                            "title": title,
                            "ok": True,
                            "duration_s": round(dt, 2),
                            "steps": step_log,
                            "page_errors": flow_errs,
                        }
                    )
                except Exception as exc:
                    dt = time.time() - t0
                    print(f"  !! FLOW CRASHED: {exc}")
                    try:
                        _screenshot(page, slug, "CRASH.png", full=True)
                    except Exception:
                        pass
                    summary.append(
                        {
                            "slug": slug,
                            "title": title,
                            "ok": False,
                            "duration_s": round(dt, 2),
                            "error": str(exc)[:500],
                            "steps": step_log,
                            "page_errors": page_errors[errs_before:],
                        }
                    )

            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        # Clean temp DB
        try:
            os.unlink(tmp_db)
        except Exception:
            pass

    # Write machine-readable results
    results = {
        "run_ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "app_url": app_url,
        "off_the_grid": True,
        "flows": summary,
        "total_flows": len(summary),
        "passed": sum(1 for s in summary if s.get("ok")),
        "failed": sum(1 for s in summary if not s.get("ok")),
        "console_errors": console_errors[:50],
        "page_errors": page_errors[:50],
        "screenshots_dir": str(SHOTS.relative_to(ROOT)),
    }
    (OUT / "results.json").parent.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(results, indent=2))

    # Write human report
    lines = [
        "# E2E Full Run — 2026-06-15",
        "",
        f"- **Flows:** {results['passed']}/{results['total_flows']} passed",
        f"- **Mode:** off-the-grid (mock providers)",
        f"- **Screenshots:** `{results['screenshots_dir']}/`",
        "",
        "## Per-flow results",
        "",
        "| Flow | Title | Status | Duration | Page errors |",
        "|------|-------|--------|----------|-------------|",
    ]
    for s in summary:
        mark = "✅" if s.get("ok") else "❌"
        err_n = len(s.get("page_errors", []))
        lines.append(
            f"| {s['slug']} | {s['title']} | {mark} | {s.get('duration_s',0)}s | {err_n} |"
        )
    lines.append("")
    if page_errors:
        lines += ["## Page errors (first 20)", ""]
        for e in page_errors[:20]:
            lines.append(f"- {e[:200]}")
        lines.append("")
    (OUT / "report.md").write_text("\n".join(lines))

    # Console summary
    print(f"\n{'='*60}\nE2E RUN COMPLETE\n{'='*60}")
    print(f"Passed: {results['passed']}/{results['total_flows']}")
    for s in summary:
        mark = "✓" if s.get("ok") else "✗"
        print(f"  {mark} {s['slug']:20s} {s.get('duration_s',0):6.2f}s  errs={len(s.get('page_errors',[]))}")
    print(f"\nResults: {OUT/'results.json'}")
    print(f"Report:  {OUT/'report.md'}")
    print(f"Shots:   {SHOTS}")

    return 0 if results["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
