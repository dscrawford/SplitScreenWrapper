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

# "eDP-1 connected primary 1280x800+0+0 right (normal left ...) 100mm x 160mm"
# -- an output's geometry on the screen, which is what the frame should fill.
_CONNECTED = re.compile(r"^(\S+) connected (primary )?(\d+)x(\d+)\+\d+\+\d+", re.MULTILINE)
# "Screen 0: minimum 320 x 200, current 1280 x 800, maximum 16384 x 16384"
_CURRENT = re.compile(r"\bcurrent\s+(\d+)\s*x\s*(\d+)")


def parse_xrandr(text: str) -> tuple[int, int] | None:
    """The screen size out of `xrandr --current`.

    An output's geometry, the primary one first: that is the size it takes
    on the screen after rotation, and one monitor's rather than the desktop
    spanning all of them. Not the starred mode -- a Steam Deck's panel is
    800x1280 and is shown rotated, so its mode is portrait while its
    geometry is 1280x800, and a frame sized from the mode came up on its
    side. The "current" figure is the fallback for an xrandr that lists no
    outputs it can size.
    """
    outputs = _CONNECTED.findall(text)
    if outputs:
        primary = [o for o in outputs if o[1]]
        _, _, width, height = (primary or outputs)[0]
        return int(width), int(height)
    current = _CURRENT.search(text)
    if current:
        return int(current.group(1)), int(current.group(2))
    return None


# Which xrandr to ask. The one on PATH, unless SPLITSCREEN_XRANDR names
# another: a test harness pretending to be a machine with a different panel
# hands over that machine's xrandr, verbatim, and a launcher's PATH prefix
# would otherwise win over anything it put in front.
XRANDR_ENV = "SPLITSCREEN_XRANDR"


def _xrandr(environ: Mapping[str, str]) -> tuple[int, int] | None:
    if not environ.get("DISPLAY"):
        return None
    try:
        done = subprocess.run(
            [environ.get(XRANDR_ENV) or "xrandr", "--current"],
            capture_output=True, text=True, timeout=5, env=dict(environ), check=False,
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
