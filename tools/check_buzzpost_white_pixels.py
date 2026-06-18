from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

from PIL import Image


def _near_white(pixel: tuple[int, ...]) -> bool:
    r, g, b = pixel[:3]
    a = pixel[3] if len(pixel) > 3 else 255
    return a > 16 and r >= 245 and g >= 245 and b >= 245


def _components(mask: list[list[bool]]) -> list[dict[str, int]]:
    h = len(mask)
    w = len(mask[0]) if h else 0
    seen = [[False] * w for _ in range(h)]
    found: list[dict[str, int]] = []
    for y in range(h):
        for x in range(w):
            if seen[y][x] or not mask[y][x]:
                continue
            q: deque[tuple[int, int]] = deque([(x, y)])
            seen[y][x] = True
            count = 0
            min_x = max_x = x
            min_y = max_y = y
            while q:
                cx, cy = q.popleft()
                count += 1
                min_x = min(min_x, cx)
                max_x = max(max_x, cx)
                min_y = min(min_y, cy)
                max_y = max(max_y, cy)
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < w and 0 <= ny < h and not seen[ny][nx] and mask[ny][nx]:
                        seen[ny][nx] = True
                        q.append((nx, ny))
            found.append(
                {
                    "x": min_x,
                    "y": min_y,
                    "width": max_x - min_x + 1,
                    "height": max_y - min_y + 1,
                    "pixels": count,
                }
            )
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--crop", default="", help="x,y,width,height")
    parser.add_argument("--max-component-pixels", type=int, default=120)
    args = parser.parse_args()

    img = Image.open(args.image).convert("RGBA")
    if args.crop:
        x, y, w, h = [int(part) for part in args.crop.split(",")]
        img = img.crop((x, y, x + w, y + h))
    pixels = img.load()
    width, height = img.size
    mask = [[_near_white(pixels[x, y]) for x in range(width)] for y in range(height)]
    bad = [
        comp
        for comp in _components(mask)
        if comp["pixels"] > args.max_component_pixels
        or (comp["width"] >= 12 and comp["height"] >= 12 and comp["pixels"] >= 32)
    ]
    if bad:
        print(f"white-pixel-check: NG {len(bad)} components")
        for comp in bad[:20]:
            print(comp)
        return 1
    print("white-pixel-check: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
