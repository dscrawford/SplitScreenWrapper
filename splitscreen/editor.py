"""Little layout editor: drag slots around, resize them, snap to edges, save.

    python3 -m splitscreen.editor examples/gotg-fsa.json           # edit that config's layout
    python3 -m splitscreen.editor --slots 3 --preset sidebar out.json

Mouse: drag a slot to move it, drag its bottom-right corner to resize.
Keys:  1 grid  2 sidebar  3 tri  4 hub   (presets, sized for the current slot count)
       A add slot   D delete selected   S save   Esc quit
Edges snap to the frame and to other slots, so covering the frame with no
black space is a matter of dragging until things click together.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from .layout import PRESETS, Frac, grid, hub, tree_fracs

SNAP_PX = 10
HANDLE_PX = 14
MIN_FRAC = 0.05
COLORS = [(230, 70, 70), (70, 130, 230), (70, 200, 90), (240, 200, 60), (200, 90, 220), (90, 200, 200)]


# ---------- pure geometry, unit-tested ----------

def snap(value: float, targets: Sequence[float], tolerance: float) -> float:
    best = min(targets, key=lambda t: abs(t - value), default=None)
    return best if best is not None and abs(best - value) <= tolerance else value


def clamp_frac(f: Frac) -> Frac:
    w, h = min(max(f.w, MIN_FRAC), 1.0), min(max(f.h, MIN_FRAC), 1.0)
    return Frac(min(max(f.x, 0.0), 1.0 - w), min(max(f.y, 0.0), 1.0 - h), w, h)


def edge_targets(slots: Sequence[Frac], skip: int) -> tuple[tuple[float, ...], tuple[float, ...]]:
    xs, ys = {0.0, 1.0}, {0.0, 1.0}
    for i, s in enumerate(slots):
        if i != skip:
            xs |= {s.x, s.x + s.w}
            ys |= {s.y, s.y + s.h}
    return tuple(sorted(xs)), tuple(sorted(ys))


def move_slot(slots: tuple[Frac, ...], i: int, x: float, y: float, tol: float) -> tuple[Frac, ...]:
    s = slots[i]
    xs, ys = edge_targets(slots, i)
    nx = snap(x, xs, tol)
    if nx == x:  # left edge did not snap: try the right edge
        nx = snap(x + s.w, xs, tol) - s.w
    ny = snap(y, ys, tol)
    if ny == y:
        ny = snap(y + s.h, ys, tol) - s.h
    new = clamp_frac(Frac(nx, ny, s.w, s.h))
    return slots[:i] + (new,) + slots[i + 1:]


def resize_slot(slots: tuple[Frac, ...], i: int, right: float, bottom: float, tol: float) -> tuple[Frac, ...]:
    s = slots[i]
    xs, ys = edge_targets(slots, i)
    new = clamp_frac(Frac(s.x, s.y, snap(right, xs, tol) - s.x, snap(bottom, ys, tol) - s.y))
    return slots[:i] + (new,) + slots[i + 1:]


def coverage(slots: Sequence[Frac], grid_n: int = 200) -> tuple[float, bool]:
    """(fraction of the frame covered, any overlap) on a coarse raster."""
    covered = overlap = 0
    for gy in range(grid_n):
        cy = (gy + 0.5) / grid_n
        for gx in range(grid_n):
            cx = (gx + 0.5) / grid_n
            hits = sum(1 for s in slots if s.x <= cx < s.x + s.w and s.y <= cy < s.y + s.h)
            covered += hits > 0
            overlap += hits > 1
    return covered / (grid_n * grid_n), overlap > 0


def preset(name: str, count: int) -> tuple[Frac, ...]:
    if name == "grid":
        return tuple(Frac(r.x / 1000, r.y / 1000, r.w / 1000, r.h / 1000) for r in grid(count, 1000, 1000))
    if name == "hub":
        return tuple(Frac(r.x / 1000, r.y / 1000, r.w / 1000, r.h / 1000) for r in hub(min(count, 5), 1000, 1000))
    if name in ("sidebar", "tri"):
        fr = tree_fracs(PRESETS[name])
        if count <= len(fr):
            return fr[:count]
        return fr + preset("grid", count - len(fr))[:0] + tuple(Frac(0, 0, 0.25, 0.25) for _ in range(count - len(fr)))
    raise ValueError(f"unknown preset {name!r}; choose grid, sidebar, tri, hub")


def layout_from_config(cfg: dict, count: int) -> tuple[Frac, ...]:
    lay = cfg.get("layout", {"name": "grid"})
    lay = {"name": lay} if isinstance(lay, str) else lay
    name = lay.get("name", "grid")
    if name == "free":
        return tuple(Frac(float(s["x"]), float(s["y"]), float(s["w"]), float(s["h"])) for s in lay.get("slots", ()))[:count]
    if name == "tree":
        return tree_fracs(lay.get("split", {}))[:count]
    if name == "hub":
        return preset("hub", count)
    return preset("grid", count)


def slot_count_from_config(cfg: dict) -> int:
    return sum(len(i.get("windows") or [None]) for i in cfg.get("instances", ()))


def save_layout(path: Path, cfg: dict, slots: Sequence[Frac]) -> dict:
    new = {**cfg, "layout": {"name": "free", "slots": [
        {"x": round(s.x, 4), "y": round(s.y, 4), "w": round(s.w, 4), "h": round(s.h, 4)} for s in slots]}}
    path.write_text(json.dumps(new, indent=2) + "\n")
    return new


# ---------- pygame front end ----------

def run_editor(path: Path, cfg: dict, slots: tuple[Frac, ...], labels: list[str], auto_save_exit: bool) -> int:
    import pygame

    W, H = 960, 540
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption(f"splitscreen layout editor - {path.name}")
    font = pygame.font.SysFont(None, 20)
    clock = pygame.time.Clock()
    tol = SNAP_PX / W
    selected: int | None = None
    mode: str | None = None  # "move" | "resize"
    grab = (0.0, 0.0)
    status = "drag slots; S saves"

    def hit(px: float, py: float) -> tuple[int | None, str | None]:
        for i in reversed(range(len(slots))):
            s = slots[i]
            rx, ry, rw, rh = s.x * W, s.y * H, s.w * W, s.h * H
            if rx <= px <= rx + rw and ry <= py <= ry + rh:
                corner = px >= rx + rw - HANDLE_PX and py >= ry + rh - HANDLE_PX
                return i, "resize" if corner else "move"
        return None, None

    running = True
    while running:
        if auto_save_exit:
            save_layout(path, cfg, slots)
            running = False
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                selected, mode = hit(*ev.pos)
                if selected is not None:
                    s = slots[selected]
                    grab = (ev.pos[0] / W - s.x, ev.pos[1] / H - s.y)
            elif ev.type == pygame.MOUSEBUTTONUP:
                mode = None
            elif ev.type == pygame.MOUSEMOTION and mode and selected is not None:
                fx, fy = ev.pos[0] / W, ev.pos[1] / H
                if mode == "move":
                    slots = move_slot(slots, selected, fx - grab[0], fy - grab[1], tol)
                else:
                    slots = resize_slot(slots, selected, fx, fy, tol)
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key == pygame.K_s:
                    save_layout(path, cfg, slots)
                    status = f"saved {len(slots)} slots to {path}"
                elif ev.key == pygame.K_a:
                    slots = slots + (Frac(0.0, 0.0, 0.25, 0.25),)
                    labels = labels + [f"slot{len(slots)}"]
                elif ev.key == pygame.K_d and selected is not None and len(slots) > 1:
                    slots = slots[:selected] + slots[selected + 1:]
                    labels = labels[:selected] + labels[selected + 1:]
                    selected = None
                elif ev.unicode in ("1", "2", "3", "4"):
                    name = {"1": "grid", "2": "sidebar", "3": "tri", "4": "hub"}[ev.unicode]
                    try:
                        slots = preset(name, len(slots))
                        status = f"preset {name}"
                    except ValueError as exc:
                        status = str(exc)

        screen.fill((12, 12, 16))
        for i, s in enumerate(slots):
            r = pygame.Rect(s.x * W, s.y * H, s.w * W, s.h * H)
            col = COLORS[i % len(COLORS)]
            pygame.draw.rect(screen, tuple(c // 3 for c in col), r)
            pygame.draw.rect(screen, col, r, 3 if i == selected else 1)
            pygame.draw.rect(screen, col, (r.right - HANDLE_PX, r.bottom - HANDLE_PX, HANDLE_PX, HANDLE_PX))
            label = f"{labels[i] if i < len(labels) else i}  {s.w:.0%} x {s.h:.0%}"
            screen.blit(font.render(label, True, (240, 240, 240)), (r.x + 6, r.y + 4))
        cov, over = coverage(slots, 60)
        hud = f"{status}   covered {cov:.0%}{'   OVERLAP' if over else ''}   keys: 1 grid 2 sidebar 3 tri 4 hub  A add  D del  S save"
        screen.blit(font.render(hud, True, (255, 220, 120) if (over or cov < 0.999) else (160, 220, 160)), (8, H - 22))
        pygame.display.flip()
        clock.tick(60)
    pygame.quit()
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config", help="session JSON to edit (created if missing)")
    ap.add_argument("--slots", type=int, help="slot count when the config has no instances")
    ap.add_argument("--preset", choices=["grid", "sidebar", "tri", "hub"], help="start from this preset")
    ap.add_argument("--save-and-exit", action="store_true", help="write the layout immediately (no window interaction)")
    args = ap.parse_args(argv)

    path = Path(args.config)
    cfg = json.loads(path.read_text()) if path.exists() else {}
    count = slot_count_from_config(cfg) or args.slots or 0
    if count < 1:
        print("no instances in config and no --slots given", file=sys.stderr)
        return 2
    labels = [w.get("id", i["id"]) for i in cfg.get("instances", ()) for w in (i.get("windows") or [{"id": i["id"]}])]
    try:
        slots = preset(args.preset, count) if args.preset else layout_from_config(cfg, count)
        if len(slots) < count:
            slots = slots + preset("grid", count)[len(slots):]
    except ValueError as exc:
        print(f"bad layout: {exc}", file=sys.stderr)
        return 2
    if args.save_and_exit:
        save_layout(path, cfg, slots)
        print(f"saved {count} slots to {path}")
        return 0
    return run_editor(path, cfg, slots, labels, auto_save_exit=False)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
