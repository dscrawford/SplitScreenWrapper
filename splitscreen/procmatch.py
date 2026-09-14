"""Map an arbitrary window's PID back to the instance that spawned it.

Games fork helpers, wrappers (gamescope, bwrap, wine) and launchers, so the
PID a compositor reports for a window is rarely the PID we spawned. Walking
the /proc parent chain until we hit a known root PID is wrapper-agnostic.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping


def parent_pid(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/stat", "rb") as fh:
            stat = fh.read()
    except OSError:
        return None
    # comm may contain spaces/parens; the ppid is the 2nd field after the last ')'
    tail = stat[stat.rfind(b")") + 2:].split()
    return int(tail[1]) if len(tail) > 1 else None


def find_instance(
    pid: int,
    roots: Mapping[int, str],
    parent_of: Callable[[int], int | None] = parent_pid,
    max_depth: int = 64,
) -> str | None:
    """Return the instance id whose root PID is `pid` or one of its ancestors."""
    cur: int | None = pid
    for _ in range(max_depth):
        if cur is None or cur <= 1:
            return None
        if cur in roots:
            return roots[cur]
        cur = parent_of(cur)
    return None
