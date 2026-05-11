#!/usr/bin/env python3
"""
generate_background.py — Generate Prady OS GRUB theme background
Phase 33: Production ISO Build

Generates a dark space-themed 1920x1080 PNG background for the GRUB boot menu.
Color palette: #0a0e1a (deep space navy) with subtle star field and gradient.

Usage:
    python3 generate_background.py
    python3 generate_background.py --width 1920 --height 1080 --output background.png

Requirements:
    pip install Pillow
"""

import argparse
import math
import random
import sys
from pathlib import Path


def generate_background(
    width: int = 1920,
    height: int = 1080,
    output_path: str = "background.png",
) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except ImportError:
        print("Error: Pillow not installed. Run: pip install Pillow", file=sys.stderr)
        sys.exit(1)

    print(f"Generating {width}x{height} Prady OS GRUB background...")

    # Base dark navy canvas
    img = Image.new("RGB", (width, height), color=(10, 14, 26))  # #0a0e1a
    draw = ImageDraw.Draw(img)

    # Subtle vertical gradient (slightly lighter at center)
    for y in range(height):
        factor = math.sin(math.pi * y / height) * 0.04
        r = int(10 + factor * 255)
        g = int(14 + factor * 255)
        b = int(26 + factor * 200)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Star field
    rng = random.Random(42)  # deterministic seed for reproducibility
    for _ in range(800):
        x = rng.randint(0, width - 1)
        y = rng.randint(0, height - 1)
        brightness = rng.randint(60, 180)
        size = rng.choices([1, 2, 3], weights=[70, 25, 5])[0]
        color = (brightness, brightness, min(255, brightness + 30))
        draw.ellipse(
            [x - size // 2, y - size // 2, x + size // 2, y + size // 2],
            fill=color,
        )

    # Subtle horizontal accent line at 20% height (below logo area)
    accent_y = int(height * 0.20)
    for x in range(width):
        factor = math.sin(math.pi * x / width)
        alpha = int(factor * 35)
        draw.point((x, accent_y), fill=(29, 111, 164, alpha))  # #1d6fa4

    # Bottom gradient fade (dark band)
    for y in range(height - 80, height):
        factor = (y - (height - 80)) / 80
        r = int(10 * (1 - factor * 0.3))
        g = int(14 * (1 - factor * 0.3))
        b = int(26 * (1 - factor * 0.2))
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Soft blur for the star field glow
    img = img.filter(ImageFilter.GaussianBlur(radius=0.4))

    # Save
    out = Path(output_path)
    img.save(out, "PNG", optimize=True)
    print(f"Background saved: {out} ({out.stat().st_size // 1024} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Prady OS GRUB background")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--output", default="background.png")
    args = parser.parse_args()
    generate_background(args.width, args.height, args.output)


if __name__ == "__main__":
    main()
