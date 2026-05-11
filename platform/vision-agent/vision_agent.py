"""Vision Agent — screen capture and understanding via multimodal models."""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GATEWAY_URL = os.getenv("MODEL_GATEWAY_URL", "http://localhost:8000")
SCREENSHOTS_DIR = Path(os.getenv("SCREENSHOTS_DIR", "/opt/kryos-os/screenshots"))
AUDIT_LOG_PATH = Path("platform/audit/vision_events.jsonl")


def _write_audit(event_type: str, data: dict) -> None:  # type: ignore[type-arg]
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {"event": event_type, "ts": time.time(), **data}
    with AUDIT_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


@dataclass
class BoundingBox:
    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> dict:  # type: ignore[type-arg]
        return asdict(self)


class VisionAgent:
    """Screen understanding agent using multimodal models via the model gateway."""

    def __init__(self, gateway_url: str = GATEWAY_URL) -> None:
        self._gateway_url = gateway_url.rstrip("/")

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    def capture_screen(self):  # type: ignore[return]
        """Capture current screen and return PIL Image."""
        try:
            import mss  # type: ignore[import-untyped]
            from PIL import Image  # type: ignore[import-untyped]
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                screenshot = sct.grab(monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                _write_audit("screen_captured", {"width": img.width, "height": img.height})
                return img
        except Exception as exc:
            logger.warning("mss capture failed (%s), using blank image", exc)
            from PIL import Image  # type: ignore[import-untyped]
            return Image.new("RGB", (1920, 1080), color=(30, 30, 30))

    def capture_screen_bytes(self) -> bytes:
        """Capture screen and return as PNG bytes."""
        image = self.capture_screen()
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()

    def _image_to_b64(self, image) -> str:  # type: ignore[return]
        """Convert PIL Image to base64 PNG string."""
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()

    # ------------------------------------------------------------------
    # Describe
    # ------------------------------------------------------------------

    async def describe_screen(self, image) -> str:  # type: ignore[return]
        """Describe the current screen state via model gateway."""
        image_b64 = self._image_to_b64(image)
        prompt = (
            "Describe what is on the screen in detail. Focus on: "
            "open windows, application names, visible text, interactive elements "
            "(buttons, text fields, menus, links), and the overall UI state. "
            "Be specific about positions (top-left, center, bottom-right etc.)."
        )
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._gateway_url}/vision/describe",
                json={"image_b64": image_b64, "prompt": prompt},
            )
            resp.raise_for_status()
            data = resp.json()
            description = data.get("description", "")
        _write_audit("screen_described", {"description_len": len(description)})
        return description

    # ------------------------------------------------------------------
    # Find element
    # ------------------------------------------------------------------

    async def find_element(self, description: str, image=None) -> Optional[BoundingBox]:
        """Find a UI element matching description and return its bounding box."""
        if image is None:
            image = self.capture_screen()
        image_b64 = self._image_to_b64(image)
        prompt = (
            f"Find the UI element described as: '{description}'. "
            'Return ONLY a JSON object like {"x": 100, "y": 200, "width": 150, "height": 40} '
            "representing the pixel bounding box. "
            "If the element is not visible, return: null"
        )
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._gateway_url}/vision/describe",
                json={"image_b64": image_b64, "prompt": prompt},
            )
            resp.raise_for_status()
            data = resp.json()
            response_text = data.get("description", "")

        # Parse bounding box from response
        try:
            json_match = re.search(r'\{[^{}]+\}', response_text)
            if json_match:
                bbox_data = json.loads(json_match.group())
                if all(k in bbox_data for k in ("x", "y", "width", "height")):
                    bbox = BoundingBox(
                        x=int(bbox_data["x"]),
                        y=int(bbox_data["y"]),
                        width=int(bbox_data["width"]),
                        height=int(bbox_data["height"]),
                    )
                    _write_audit("element_found", {"description": description, "bbox": bbox.to_dict()})
                    return bbox
        except (ValueError, KeyError):
            pass
        _write_audit("element_not_found", {"description": description})
        return None
