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


@dataclass(frozen=True)
class Frac:
    """A slot as fractions of the frame, the unit the editor works in."""
    x: float
    y: float
    w: float
    h: float

    def to_rect(self, width: int, height: int) -> Rect:
        x0, y0 = round(self.x * width), round(self.y * height)
        x1, y1 = round((self.x + self.w) * width), round((self.y + self.h) * height)
        return Rect(x0, y0, max(1, x1 - x0), max(1, y1 - y0))


def frac_from_dict(d: dict) -> Frac:
    try:
        f = Frac(float(d["x"]), float(d["y"]), float(d["w"]), float(d["h"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"slot needs numeric x, y, w, h: {d!r}") from exc
    if not (0 <= f.x <= 1 and 0 <= f.y <= 1 and 0 < f.w <= 1 and 0 < f.h <= 1):
        raise ValueError(f"slot fractions must lie inside the frame: {d!r}")
    return f


def free(count: int, width: int, height: int, slots: list | tuple = ()) -> tuple[Rect, ...]:
    """Explicit slots as fractions of the frame; what the editor saves."""
    fracs = tuple(f if isinstance(f, Frac) else frac_from_dict(f) for f in slots)
    if len(fracs) != count:
        raise ValueError(f"free layout has {len(fracs)} slots but {count} are needed")
    return tuple(f.to_rect(width, height) for f in fracs)


def tree_fracs(node: dict, x: float = 0.0, y: float = 0.0, w: float = 1.0, h: float = 1.0) -> tuple[Frac, ...]:
    """Recursive binary/n-ary splits, i3-style, so nothing is ever left uncovered.

    node = {} is a leaf. Otherwise {"split": "h"|"v", "children": [...], "ratio": [..]}
    where ratio (optional) gives each child's share and defaults to equal shares.
    Leaves are numbered depth-first, left to right; that is the slot order.
    """
    children = node.get("children")
    if not children:
        return (Frac(x, y, w, h),)
    direction = node.get("split", "h")
    if direction not in ("h", "v"):
        raise ValueError(f"split must be 'h' or 'v', got {direction!r}")
    ratio = node.get("ratio") or [1.0] * len(children)
    if len(ratio) != len(children) or any(r <= 0 for r in ratio):
        raise ValueError("ratio must list one positive share per child")
    total = float(sum(ratio))
    out: list[Frac] = []
    offset = 0.0
    for child, share in zip(children, ratio):
        part = share / total
        if direction == "h":
            out.extend(tree_fracs(child, x + offset * w, y, part * w, h))
        else:
            out.extend(tree_fracs(child, x, y + offset * h, w, part * h))
        offset += part
    return tuple(out)


def tree(count: int, width: int, height: int, split: dict | None = None) -> tuple[Rect, ...]:
    fracs = tree_fracs(split or {})
    if len(fracs) != count:
        raise ValueError(f"tree layout has {len(fracs)} leaves but {count} slots are needed")
    return tuple(f.to_rect(width, height) for f in fracs)


# Ready-made trees. Slot order is depth-first, so for "sidebar" the two stacked
# side slots come first and the big one last; configs list instances accordingly.
PRESETS: dict[str, dict] = {
    "grid4": {"split": "v", "children": [
        {"split": "h", "children": [{}, {}]}, {"split": "h", "children": [{}, {}]}]},
    "sidebar": {"split": "h", "ratio": [1, 3], "children": [
        {"split": "v", "children": [{}, {}]}, {}]},
    "tri": {"split": "v", "children": [
        {"split": "h", "children": [{}, {}]}, {}]},
}

LAYOUTS = {"grid": grid, "hub": hub, "free": free, "tree": tree}


def compute(name: str, count: int, width: int, height: int, **kwargs) -> tuple[Rect, ...]:
    try:
        fn = LAYOUTS[name]
    except KeyError as exc:
        raise ValueError(f"unknown layout {name!r}; choose from {sorted(LAYOUTS)}") from exc
    return fn(count, width, height, **kwargs)
