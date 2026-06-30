"""Capture Argus GUI screenshots for promotional materials."""

from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

BASE_URL = "http://127.0.0.1:18793"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "images" / "screenshots"


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def capture_tree(page) -> None:
    print("Capturing tree...")
    await page.goto(BASE_URL)
    await page.wait_for_timeout(1500)
    await page.screenshot(path=OUTPUT_DIR / "argus-gui-tree.png")
    print("Tree captured.")


async def switch_view(page, name: str) -> None:
    await page.click(f"nav button:has-text('{name}')")
    await page.wait_for_timeout(800)


async def capture_chat(page) -> None:
    print("Capturing chat...")
    await page.goto(BASE_URL)
    await page.wait_for_timeout(1500)
    await switch_view(page, "Chat")
    await page.wait_for_selector(".composer textarea", state="visible")
    await page.screenshot(path=OUTPUT_DIR / "argus-gui-chat.png")
    print("Chat captured.")


async def capture_meeting(page) -> None:
    print("Capturing meeting...")
    await page.goto(BASE_URL)
    await page.wait_for_timeout(1500)
    await switch_view(page, "Meeting")
    await page.wait_for_selector("select", state="visible")
    await page.screenshot(path=OUTPUT_DIR / "argus-gui-meeting.png")
    print("Meeting captured.")


async def capture_status(page) -> None:
    print("Capturing status...")
    await page.goto(BASE_URL)
    await page.wait_for_timeout(1500)
    await switch_view(page, "Status")
    await page.wait_for_selector("table", state="visible")
    await page.screenshot(path=OUTPUT_DIR / "argus-gui-status.png")
    print("Status captured.")


async def main() -> int:
    ensure_output_dir()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="msedge")
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        await capture_tree(page)
        await capture_chat(page)
        await capture_meeting(page)
        await capture_status(page)

        await browser.close()

    print(f"Screenshots saved to {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
