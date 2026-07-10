"""Generate promotional images for Argus showcase.

Uses the Trae text-to-image API. The API is asynchronous; this script polls
until the real image is returned (size differs from the placeholder).
"""

from __future__ import annotations

import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE_URL = "https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image"
PLACEHOLDER_SIZE = 176_626
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "docs" / "images"

IMAGES = {
    "collaboration-tree.png": (
        "A clean dark-themed digital dashboard showing a node graph collaboration "
        "tree with human nodes and AI agent nodes connected by directional edges, "
        "modern SaaS UI design, blue and cyan accents, technical visualization, "
        "high detail, 4k"
    ),
    "meeting-takeover.png": (
        "A futuristic control room interface showing an AI multi-agent meeting "
        "in progress with a human supervisor pressing a skip-turn button, "
        "holographic chat bubbles, dark theme with green and blue highlights, "
        "cinematic lighting"
    ),
    "inbox-persistence.png": (
        "A digital inbox interface showing offline message persistence for a "
        "human user, with messages flowing into a secure storage vault while "
        "AI agents continue working, dark tech aesthetic, cyan and orange accents"
    ),
    "argus-hero.png": (
        "A wide cinematic hero banner for an AI multi-agent collaboration "
        "platform called Argus, showing a human orchestrator connected to "
        "multiple AI agent avatars through a glowing network, dark blue "
        "background, futuristic, professional"
    ),
}


def download_image(filename: str, prompt: str, max_wait: int = 120) -> Path:
    """Poll the text-to-image endpoint until the real image is returned."""
    url = f"{BASE_URL}?prompt={urllib.parse.quote(prompt)}&image_size=landscape_16_9"
    path = OUTPUT_DIR / filename
    deadline = time.time() + max_wait
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        urllib.request.urlretrieve(url, path)
        size = path.stat().st_size
        print(f"[{filename}] attempt {attempt}: {size} bytes")
        if size != PLACEHOLDER_SIZE:
            return path
        time.sleep(10)
    raise TimeoutError(f"Image {filename} did not become ready within {max_wait}s")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, prompt in IMAGES.items():
        try:
            path = download_image(filename, prompt)
            print(f"  -> {path}")
        except Exception as exc:
            print(f"  ERROR: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
