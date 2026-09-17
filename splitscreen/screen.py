"""How big the screen is, asked of the host rather than assumed.

A frame size used to be written into the config -- 1920x1080, because that is
what the machine it was written on had -- and a nested compositor of that size
on a Steam Deck's 1280x800 panel hangs off the edge with a player's Game Boy
somewhere past the bezel. The layouts are already fractions of the frame; this
is the frame following the screen.

Two questions, in order: an X display (which under gamescope, KDE's Xwayland
and a plain X session is the one that is there) through xrandr, and a sway or
i3 host through its socket. Neither answering leaves the size to the nested
compositor's own default, which is also what a config that names no frame got
before.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping

# "Screen 0: minimum 320 x 200, current 1280 x 800, maximum 16384 x 16384"
_CURRENT = re.compile(r"\bcurrent\s+(\d+)\s*x\s*(\d+)")
# "   1280x800      60.00*+   59.99" -- the mode in use carries the star.
_STARRED = re.compile(r"^\s*(\d+)x(\d+)\s.*\*", re.MULTILINE)


def parse_xrandr(text: str) -> tuple[int, int] | None:
    """The screen size out of `xrandr --current`.

    The starred mode first: on a multi-monitor X screen the "current" figure
    is the whole virtual desktop, and a frame that size straddles two
    monitors. The virtual size is the fallback for an xrandr that lists no
    modes -- Xwayland under gamescope reports one output and no star on some
    versions.
    """
    starred = _STARRED.search(text)
    if starred:
        return int(starred.group(1)), int(starred.group(2))
    current = _CURRENT.search(text)
    if current:
        return int(current.group(1)), int(current.group(2))
    return None


def _xrandr(environ: Mapping[str, str]) -> tuple[int, int] | None:
    if not environ.get("DISPLAY"):
        return None
    try:
        done = subprocess.run(
            ["xrandr", "--current"], capture_output=True, text=True, timeout=5, env=dict(environ), check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_xrandr(done.stdout) if done.returncode == 0 else None


def _sway(environ: Mapping[str, str]) -> tuple[int, int] | None:
    sock = environ.get("SWAYSOCK") or environ.get("I3SOCK")
    if not sock:
        return None
    try:
        import i3ipc

        outputs = i3ipc.Connection(socket_path=sock).get_outputs()
    except Exception:  # not a sway or i3 host after all, or one that refuses
        return None
    for output in outputs:
        if output.active and output.rect.width > 0 and output.rect.height > 0:
            return output.rect.width, output.rect.height
    return None


def host_screen_size(environ: Mapping[str, str] | None = None) -> tuple[int, int] | None:
    """The size of the screen this session will be shown on, or None when
    nobody can say."""
    env = os.environ if environ is None else environ
    return _xrandr(env) or _sway(env)
