"""Pure layout math: map N instances onto rectangles inside a frame.

Every function returns a new tuple of Rect objects; nothing is mutated.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int


def grid(count: int, width: int, height: int) -> tuple[Rect, ...]:
    """Tile `count` slots in the most square grid that fits.

    1 -> full frame, 2 -> side by side, 3-4 -> 2x2, 5-6 -> 3x2, 7-9 -> 3x3 ...
    A 3-slot grid leaves the bottom-right cell empty rather than stretching.
    """
    if count < 1:
        raise ValueError("count must be >= 1")
    cols = math.ceil(math.sqrt(count))
    rows = math.ceil(count / cols)
    cell_w, cell_h = width // cols, height // rows
    return tuple(
        Rect((i % cols) * cell_w, (i // cols) * cell_h, cell_w, cell_h)
        for i in range(count)
    )


def hub(count: int, width: int, height: int, center_fraction: float = 0.5) -> tuple[Rect, ...]:
    """One central slot plus up to four corner slots (Four Swords Adventures style).

    Slot 0 is the center. Slots 1-4 are TL, TR, BL, BR corners.
    The center takes `center_fraction` of each axis; corners take the remainder
    on each side. Requires 1 <= count <= 5.
    """
    if not 1 <= count <= 5:
        raise ValueError("hub layout supports 1 to 5 slots")
    if not 0.0 < center_fraction < 1.0:
        raise ValueError("center_fraction must be in (0, 1)")
    cw, ch = int(width * center_fraction), int(height * center_fraction)
    side_w, side_h = (width - cw) // 2, (height - ch) // 2
    center = Rect(side_w, side_h, cw, ch)
    corners = (
        Rect(0, 0, side_w, side_h),
        Rect(width - side_w, 0, side_w, side_h),
        Rect(0, height - side_h, side_w, side_h),
        Rect(width - side_w, height - side_h, side_w, side_h),
    )
    return (center, *corners)[:count]


LAYOUTS = {"grid": grid, "hub": hub}


def compute(name: str, count: int, width: int, height: int, **kwargs) -> tuple[Rect, ...]:
    try:
        fn = LAYOUTS[name]
    except KeyError as exc:
        raise ValueError(f"unknown layout {name!r}; choose from {sorted(LAYOUTS)}") from exc
    return fn(count, width, height, **kwargs)
