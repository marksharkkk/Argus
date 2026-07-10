"""Capture Argus GUI meeting screenshot only."""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:18793"
OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "images" / "screenshots" / "argus-gui-meeting.png"

async def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="msedge")
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        await page.goto(BASE_URL)
        await page.wait_for_timeout(1500)
        print("Clicking Meeting...")
        await page.click("nav button:has-text('Meeting')")
        await page.wait_for_timeout(800)
        print("Filling form...")
        await page.select_option("select", "dev")
        await page.check("input[type='checkbox'][value='human']")
        await page.fill("input[type='text']", "产品迭代规划会议")
        print("Creating meeting...")
        await page.click("button:has-text('发起会议')")
        await page.wait_for_timeout(2500)
        print("Taking screenshot...")
        await page.screenshot(path=str(OUTPUT))
        await browser.close()
    print(f"Saved {OUTPUT}")
    return 0

if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
