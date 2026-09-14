"""Build a bubblewrap command line that hides every input device except the
ones assigned to this instance. This is the same trick PartyDeck uses and it
is fully game-agnostic: the game's input library (SDL, evdev, hidapi) simply
never sees the other players' devices.
"""
from __future__ import annotations

import os
from collections.abc import Sequence


def sibling_nodes(event_path: str) -> tuple[str, ...]:
    """Legacy /dev/input/jsN nodes that belong to the same device as `event_path`."""
    name = os.path.basename(event_path)
    sysdir = f"/sys/class/input/{name}/device"
    try:
        entries = os.listdir(sysdir)
    except OSError:
        return ()
    return tuple(f"/dev/input/{e}" for e in sorted(entries) if e.startswith("js"))


def hidraw_siblings(event_path: str) -> tuple[str, ...]:
    """/dev/hidraw* nodes that share a HID parent with `event_path`.

    SDL (via hidapi) talks to many controllers over hidraw instead of evdev,
    so an allowed device must keep its hidraw node and all others must lose it.
    """
    name = os.path.basename(event_path)
    try:
        hid_parent = os.path.realpath(f"/sys/class/input/{name}/device/device")
        return tuple(sorted(f"/dev/{n}" for n in os.listdir(os.path.join(hid_parent, "hidraw"))))
    except OSError:
        return ()


def all_hidraw_nodes() -> tuple[str, ...]:
    try:
        return tuple(sorted(f"/dev/{n}" for n in os.listdir("/dev") if n.startswith("hidraw")))
    except OSError:
        return ()


def bwrap_argv(
    command: Sequence[str],
    allowed_devices: Sequence[str],
    extra_binds: Sequence[tuple[str, str]] = (),
    bwrap: str = "bwrap",
) -> tuple[str, ...]:
    """Wrap `command` so only `allowed_devices` exist under /dev/input.

    `extra_binds` are (host_path, sandbox_path) pairs, e.g. for per-player
    save directories. Paths are dev-bound so device nodes keep working.
    """
    argv: list[str] = [bwrap, "--die-with-parent", "--dev-bind", "/", "/", "--tmpfs", "/dev/input"]
    keep_hidraw: set[str] = set()
    for dev in allowed_devices:
        argv += ["--dev-bind", dev, dev]
        for js in sibling_nodes(dev):
            argv += ["--dev-bind", js, js]
        keep_hidraw |= set(hidraw_siblings(dev))
    # hidraw nodes live directly under /dev, so they are masked one by one instead of via tmpfs.
    for node in all_hidraw_nodes():
        if node not in keep_hidraw:
            argv += ["--bind", "/dev/null", node]
    for host, inner in extra_binds:
        argv += ["--bind", host, inner]
    argv += ["--", *command]
    return tuple(argv)
