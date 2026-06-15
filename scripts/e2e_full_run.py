"""Full end-to-end user flow test for ShopStack.

Boots the Gradio app, drives every flow headlessly, captures screenshots,
AND records actual video of every flow using Playwright's
``record_video_dir`` browser context option. Uses REAL local models.

The output directory contains:
- ``screenshots/<flow>/<step>.png`` — per-step screenshots
- ``videos/<flow>.webm`` — per-flow WebM video recordings
  (encoded by Playwright from the actual browser rendering)
- ``videos/e2e_recording.mp4`` — combined MP4 slideshow of all
  screenshots (for sharing when WebM isn't supported)

Usage: uv run python scripts/e2e_full_run.py
"""
from __future__ import annotations
import json, os, shutil, socket, subprocess, sys, time, tempfile, urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Docs" / "qa" / "2026-06-15_e2e_audit_run"
SHOTS = OUT / "screenshots"
VIDEOS = OUT / "videos"
# Per-flow video recordings. The directory is wiped at the start
# of each run so stale videos from prior runs don't accumulate.
FLOW_VIDEOS = OUT / "flow_videos"

IMG_FRESH_MART = ROOT / "data" / "fresh_mart.png"
IMG_MAA_LAXMI = ROOT / "data" / "maa_laxmi.png"
IMG_SAI_PHARMA = ROOT / "data" / "sai_pharma.png"
IMG_FRIDGE = ROOT / "benchmarks" / "modal" / "assets" / "household_grounding" / "fridge.png"

def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]

def _wait_for_server(url, timeout=90.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try: urllib.request.urlopen(url, timeout=3); return True
        except: time.sleep(1.0)
    return False

def _dismiss(page):
    page.execute_script("""() => {
        var t = document.getElementById('tour-overlay');
        if (t) { t.style.display = 'none'; t.removeAttribute('data-active'); }
        try { localStorage.setItem('shopstack.tour.shown', '1'); } catch(e) {}
        var w = document.getElementById('onboarding-wizard');
        if (w) { var b = w.querySelectorAll('button');
            for (var i=0;i<b.length;i++) { if((b[i].textContent||'').indexOf('Skip')!=-1) {try{b[i].click();}catch(e){}break;} }
            w.style.display = 'none'; }
        document.querySelectorAll('[aria-modal="true"]').forEach(function(el){ if(el.id!='tour-overlay'&&el.id!='onboarding-wizard') el.style.display='none'; });
    }""")

def _click_tab(page, text):
    for sel in ("button[role='tab']:has-text('%s')" % text, "button:has-text('%s')" % text):
        try: page.locator(sel).first.click(timeout=5000); return True
        except: continue
    return False

def _click_subtab(page, text):
    for sel in ("button[role='tab']:has-text('%s')" % text, "button:has-text('%s')" % text):
        try:
            loc = page.locator(sel)
            if loc.count() == 0: continue
            loc.last.click(timeout=4000, force=True); return True
        except: continue
    return False

def _shot(page, flow, name, full=False):
    path = SHOTS / flow / name
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=full)
    return str(path.relative_to(ROOT))

FLOWS = [
    {"slug":"01_boot","title":"Boot → Home","steps":[{"kind":"goto"},{"kind":"wait","ms":5000},{"kind":"dismiss"},{"kind":"shot","name":"01_home.png","full":True}]},
    {"slug":"02_pantry","title":"Pantry","steps":[{"kind":"dismiss"},{"kind":"tab","text":"Pantry"},{"kind":"wait","ms":2500},{"kind":"shot","name":"02_pantry.png","full":True}]},
    {"slug":"03_shopping","title":"Shopping","steps":[{"kind":"dismiss"},{"kind":"tab","text":"Shopping"},{"kind":"wait","ms":2500},{"kind":"shot","name":"03_shopping.png","full":True}]},
    {"slug":"04_shelf_scan","title":"Shelf Scan (vision OCR fresh_mart.png)","steps":[{"kind":"dismiss"},{"kind":"tab","text":"Shopping"},{"kind":"wait","ms":1500},{"kind":"subtab","text":"Shelf Scan"},{"kind":"wait","ms":2000},{"kind":"shot","name":"04a_shelf_open.png"},{"kind":"upload","path":str(IMG_FRESH_MART)},{"kind":"wait","ms":15000},{"kind":"shot","name":"04b_shelf_after.png","full":True}]},
    {"slug":"05_recipe_scan","title":"Recipe Scan (OCR maa_laxmi.png)","steps":[{"kind":"dismiss"},{"kind":"tab","text":"Shopping"},{"kind":"wait","ms":1500},{"kind":"subtab","text":"Recipe Scan"},{"kind":"wait","ms":2000},{"kind":"shot","name":"05a_recipe_open.png"},{"kind":"upload","path":str(IMG_MAA_LAXMI)},{"kind":"wait","ms":15000},{"kind":"shot","name":"05b_recipe_after.png","full":True}]},
    {"slug":"06_market_intel","title":"Market Intel (sai_pharma.png)","steps":[{"kind":"dismiss"},{"kind":"tab","text":"Shopping"},{"kind":"wait","ms":1500},{"kind":"subtab","text":"Market Intel"},{"kind":"wait","ms":2000},{"kind":"shot","name":"06a_intel_open.png"},{"kind":"upload","path":str(IMG_SAI_PHARMA)},{"kind":"wait","ms":15000},{"kind":"shot","name":"06b_intel_after.png","full":True}]},
    {"slug":"07_recipes","title":"Recipes","steps":[{"kind":"dismiss"},{"kind":"tab","text":"Recipes"},{"kind":"wait","ms":2500},{"kind":"shot","name":"07_recipes.png","full":True}]},
    {"slug":"08_trips","title":"Trips","steps":[{"kind":"dismiss"},{"kind":"tab","text":"Trips"},{"kind":"wait","ms":2500},{"kind":"shot","name":"08_trips.png","full":True}]},
    {"slug":"09_photo_map","title":"Pantry Photo Map (grounding fridge.png)","steps":[{"kind":"dismiss"},{"kind":"tab","text":"Pantry"},{"kind":"wait","ms":1500},{"kind":"subtab","text":"Photo Map"},{"kind":"wait","ms":2000},{"kind":"shot","name":"09a_photo_map.png"},{"kind":"upload","path":str(IMG_FRIDGE)},{"kind":"wait","ms":15000},{"kind":"shot","name":"09b_photo_map_after.png","full":True}]},
    {"slug":"10_memory","title":"Memory","steps":[{"kind":"dismiss"},{"kind":"tab","text":"Memory"},{"kind":"wait","ms":2500},{"kind":"shot","name":"10_memory.png","full":True}]},
]

def run_step(page, step, flow_slug, app_url):
    kind = step["kind"]
    if kind == "goto": page.goto(app_url, wait_until="domcontentloaded", timeout=30000); return "navigated"
    if kind == "wait": page.wait_for_timeout(step["ms"]); return "waited %dms" % step["ms"]
    if kind == "dismiss": _dismiss(page); return "dismissed"
    if kind == "shot": return "screenshot -> " + _shot(page, flow_slug, step["name"], step.get("full",False))
    if kind == "tab": return "tab '%s': %s" % (step["text"], "ok" if _click_tab(page, step["text"]) else "NOT FOUND")
    if kind == "subtab": return "subtab '%s': %s" % (step["text"], "ok" if _click_subtab(page, step["text"]) else "NOT FOUND")
    if kind == "upload":
        try: page.set_input_files("input[type='file']", step["path"], timeout=5000); return "uploaded %s" % Path(step["path"]).name
        except Exception as exc: return "upload FAILED: %s" % exc
    return "unknown: %s" % kind

def _encode_video():
    shots = sorted(s for s in SHOTS.rglob("*.png") if "CRASH" not in s.name)
    if not shots: return None
    list_file = VIDEOS / "frames.txt"
    with open(list_file, "w") as f:
        for s in shots: f.write("file '%s'\nduration 3\n" % s.absolute())
        f.write("file '%s'\n" % shots[-1].absolute())
    output = VIDEOS / "e2e_recording.mp4"
    cmd = ["ffmpeg","-y","-f","concat","-safe","0","-i",str(list_file),
           "-vf","scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2",
           "-c:v","libx264","-pix_fmt","yuv420p","-r","24",str(output)]
    try: subprocess.run(cmd, capture_output=True, timeout=60, check=True); return str(output.relative_to(ROOT))
    except Exception as exc: print("ffmpeg failed: %s" % exc); return None

def main():
    from playwright.sync_api import sync_playwright
    SHOTS.mkdir(parents=True, exist_ok=True)
    VIDEOS.mkdir(parents=True, exist_ok=True)
    # Reset per-flow video dir at start of run
    if FLOW_VIDEOS.exists():
        shutil.rmtree(FLOW_VIDEOS)
    FLOW_VIDEOS.mkdir(parents=True, exist_ok=True)
    port = _free_port()
    app_url = "http://127.0.0.1:%d" % port
    print("Booting ShopStack on port %d ..." % port)
    tmp_db = tempfile.mktemp(suffix=".db")
    proc_env = {**os.environ, "SHOPSTACK_DB_PATH": tmp_db}
    proc = subprocess.Popen([sys.executable,"app.py","--port",str(port)], cwd=str(ROOT), env=proc_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    summary = []; console_errors = []; page_errors = []; flow_videos = {}
    try:
        if not _wait_for_server(app_url, 60):
            out = proc.stdout.read(2000) if proc.stdout else ""
            print("SERVER FAILED:\n%s" % out); return 1
        print("Server up at %s" % app_url)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for flow in FLOWS:
                slug = flow["slug"]; title = flow["title"]
                print("\n%s\n%s :: %s\n%s" % ("="*60, slug, title, "="*60))
                t0 = time.time()
                # Create a fresh context per flow with its own video dir
                flow_video_dir = FLOW_VIDEOS / slug
                flow_video_dir.mkdir(parents=True, exist_ok=True)
                ctx = browser.new_context(
                    viewport={"width": 1440, "height": 900},
                    record_video_dir=str(flow_video_dir),
                    record_video_size={"width": 1280, "height": 720},
                )
                page = ctx.new_page()
                errs_before = len(page_errors)
                step_log = []
                flow_console = []
                page.on("console", lambda msg: (
                    flow_console.append(msg.text[:300]) if msg.type == "error" else None,
                    console_errors.append(msg.text[:300]) if msg.type == "error" else None,
                ))
                page.on("pageerror", lambda err: page_errors.append(str(err)[:500]))
                try:
                    for step in flow["steps"]:
                        msg = run_step(page, step, slug, app_url)
                        print("  -> %s" % msg); step_log.append(msg)
                    dt = time.time() - t0
                    flow_errs = page_errors[errs_before:]
                    summary.append({"slug":slug,"title":title,"ok":True,"duration_s":round(dt,2),"steps":step_log,"page_errors":flow_errs})
                except Exception as exc:
                    dt = time.time() - t0; print("  !! CRASHED: %s" % exc)
                    try: _shot(page, slug, "CRASH.png", True)
                    except: pass
                    summary.append({"slug":slug,"title":title,"ok":False,"duration_s":round(dt,2),"error":str(exc)[:500],"steps":step_log,"page_errors":page_errors[errs_before:]})
                finally:
                    # Close page + context to flush video file
                    try: page.close()
                    except: pass
                    try: ctx.close()
                    except: pass
                    # Find the produced webm and move it to a stable name
                    webms = list(flow_video_dir.glob("*.webm"))
                    if webms:
                        src = max(webms, key=lambda p: p.stat().st_mtime)
                        dst = VIDEOS / (slug + ".webm")
                        try:
                            shutil.copy2(src, dst)
                            flow_videos[slug] = str(dst.relative_to(ROOT))
                            print("  video -> %s" % flow_videos[slug])
                        except Exception as exc:
                            print("  video copy failed: %s" % exc)
            browser.close()
    finally:
        proc.terminate()
        try: proc.wait(timeout=10)
        except: proc.kill()
        try: os.unlink(tmp_db)
        except: pass

    print("\nEncoding MP4 slideshow from screenshots...")
    video_path = _encode_video()
    results = {"run_ts":time.strftime("%Y-%m-%dT%H:%M:%S%z"),"app_url":app_url,"off_the_grid":False,
               "flows":summary,"total_flows":len(summary),
               "passed":sum(1 for s in summary if s.get("ok")),"failed":sum(1 for s in summary if not s.get("ok")),
               "console_errors":console_errors[:50],"page_errors":page_errors[:50],
               "screenshots_dir":str(SHOTS.relative_to(ROOT)),"videos_dir":str(VIDEOS.relative_to(ROOT)),
               "flow_videos":flow_videos,"video_file":video_path or ""}
    (OUT/"results.json").parent.mkdir(parents=True, exist_ok=True)
    (OUT/"results.json").write_text(json.dumps(results, indent=2))
    print("\n%s\nE2E RUN COMPLETE\n%s" % ("="*60,"="*60))
    print("Passed: %d/%d" % (results["passed"], results["total_flows"]))
    for s in summary:
        print("  %s %s" % ("✓" if s.get("ok") else "✗", s["slug"]))
    if video_path: print("\nSlideshow MP4: %s" % video_path)
    if flow_videos: print("Per-flow WebM videos in: %s/" % VIDEOS.relative_to(ROOT))
    print("Results: %s" % (OUT/"results.json"))
    return 0 if results["failed"]==0 else 1

if __name__ == "__main__":
    sys.exit(main())
