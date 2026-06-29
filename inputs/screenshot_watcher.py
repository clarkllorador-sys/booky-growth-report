#!/usr/bin/env python3
"""
screenshot_watcher.py
Watches the project root folder for trigger files written by Claude.
When found: screenshots the report HTML using local Playwright, saves the PNG to outputs/.
That's it — no network access, no data sent anywhere, only reads/writes this folder.
"""
import time, asyncio
from pathlib import Path

WATCH_DIR = Path(__file__).parent.parent          # project root (growth_daily_reports_v4/)
OUTPUT_DIR = WATCH_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)
POLL_INTERVAL = 2  # seconds between checks

async def take_screenshot(standalone_html: Path, out_png: Path):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-gpu"])
        page = await browser.new_page(viewport={"width": 1200, "height": 900})
        await page.goto(f"file://{standalone_html}", wait_until="networkidle")
        await page.wait_for_selector("#dgr-report", timeout=15000)
        await page.wait_for_timeout(1200)
        el = await page.query_selector("#dgr-report")
        box = await el.bounding_box()
        await page.set_viewport_size({"width": int(box["width"]) + 40, "height": int(box["height"]) + 40})
        await page.wait_for_timeout(400)
        await (await page.query_selector("#dgr-report")).screenshot(path=str(out_png))
        await browser.close()

def process(trigger: Path):
    date = trigger.stem.replace("screenshot_trigger_", "")
    html = WATCH_DIR / f"report_{date}_standalone.html"
    png  = OUTPUT_DIR / f"report_{date}.png"
    done = WATCH_DIR / f"screenshot_done_{date}.txt"
    err  = WATCH_DIR / f"screenshot_error_{date}.txt"
    done.unlink(missing_ok=True)
    err.unlink(missing_ok=True)
    trigger.unlink()  # consume trigger immediately
    try:
        asyncio.run(take_screenshot(html, png))
        done.write_text(str(png))
        print(f"[watcher] ✓ {png.name}")
    except Exception as e:
        err.write_text(str(e))
        print(f"[watcher] ✗ {e}")

print(f"[watcher] Ready — watching {WATCH_DIR}")
while True:
    for f in WATCH_DIR.glob("screenshot_trigger_*.txt"):
        process(f)
    time.sleep(POLL_INTERVAL)
