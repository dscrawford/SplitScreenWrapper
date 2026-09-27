"""Bind controllers to Dolphin's integrated GBA ports (GBA.ini).

Dolphin keeps GBA bindings in <config>/dolphin-emu/GBA.ini, one [GBAn] section
per port, and reads it at startup. Nothing on the command line can set it, so
this runs as a `pre_launch` step of a split-screen instance:

    python3 -m splitscreen.handlers.dolphin_gba --config-dir ~/.config \\
        --gba "1=sdl:Xbox 360 Controller" --gba 2=keyboard

Device forms: `pad:N` = the Nth controller in the list `--pads-cmd` prints (see
`pads_from_json`); without one there is nothing to count, and it is the keyboard --
`sdl:<Name>` = "SDL/0/<Name>" verbatim -- the way for a caller that knows which
device it means (a controller service's virtual pads, say) to say so --
`keyboard` = Dolphin's stock key map.
A `pad:N` that is not plugged in falls back to the keyboard with a warning, so
a missing second controller never blocks the launch.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

PAD_BINDINGS = """\
Buttons/B = `Button E`
Buttons/A = `Button S`
Buttons/L = `Shoulder L`
Buttons/R = `Shoulder R`
Buttons/SELECT = `Back`
Buttons/START = `Start`
D-Pad/Up = `Pad N`|`Left Y+`
D-Pad/Down = `Pad S`|`Left Y-`
D-Pad/Left = `Pad W`|`Left X-`
D-Pad/Right = `Pad E`|`Left X+`
"""

KEYBOARD_DEVICE = "XInput2/0/Virtual core pointer"
KEYBOARD_BINDINGS = """\
Buttons/B = `Z`
Buttons/A = `X`
Buttons/L = `Q`
Buttons/R = `W`
Buttons/SELECT = `BackSpace`
Buttons/START = `Return`
D-Pad/Up = `T`
D-Pad/Down = `G`
D-Pad/Left = `F`
D-Pad/Right = `H`
"""


def gba_section(port: int, device: str) -> str:
    """Pure: one [GBAn] section. Keyboard gets Dolphin's default keys, anything else the pad map."""
    if not 1 <= port <= 4:
        raise ValueError("GBA port must be 1..4")
    body = KEYBOARD_BINDINGS if device == KEYBOARD_DEVICE else PAD_BINDINGS
    return f"[GBA{port}]\nDevice = {device}\n{body}"


def rewrite(existing: str, sections: Mapping[int, str]) -> str:
    """Pure: replace the given [GBAn] sections, keep every other section verbatim.

    Ports not in `sections` keep their old text (unlike GCPad, an untouched GBA
    port is harmless: it just keeps whatever it had).
    """
    parts = re.split(r"(?m)^(?=\[)", existing)
    kept = [p for p in parts if p.strip() and not any(p.startswith(f"[GBA{n}]") for n in sections)]
    new = [sections[n] for n in sorted(sections)]
    text = "".join(p if p.endswith("\n") else p + "\n" for p in kept + new)
    return text


def parse_device(spec: str, pads: Sequence[str], warn=print) -> str:
    """Pure given `pads` (Dolphin device strings in slot order)."""
    if spec == "keyboard":
        return KEYBOARD_DEVICE
    if spec.startswith("sdl:"):
        return f"SDL/0/{spec[4:]}"
    if spec.startswith("pad:"):
        try:
            idx = int(spec[4:])
        except ValueError as exc:
            raise ValueError(f"bad pad index in {spec!r}") from exc
        if idx < len(pads):
            return pads[idx]
        warn(f"dolphin_gba: pad:{idx} is not connected ({len(pads)} pad(s) listed"
             f"{'' if pads else ' -- is --pads-cmd set?'}); using keyboard")
        return KEYBOARD_DEVICE
    raise ValueError(f"unknown device spec {spec!r}; use pad:N, sdl:<name> or keyboard")


def pads_from_json(output: str) -> tuple[str, ...]:
    """Pure: a pad list as JSON -> Dolphin device strings, in the list's order.

    One object per controller, `{"name": ..., "slot": N, "gamepad": true}`:
    `slot` counts how many pads of the same name came before this one, which is
    how Dolphin tells two identical pads apart, and anything whose `gamepad` is
    false is skipped. The order is the list's own -- whatever order the caller
    means by player one, two, three.
    """
    try:
        rows = json.loads(output)
    except ValueError:
        return ()
    if not isinstance(rows, list):
        return ()
    rows = [r for r in rows if isinstance(r, dict) and r.get("gamepad", True) and r.get("name")]
    return tuple(f"SDL/{int(r.get('slot', 0))}/{r['name']}" for r in rows)


def _run(argv: list[str], timeout: int = 20) -> str:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def detect_pads(command: str | None) -> tuple[str, ...]:
    """Every pad, in player order, as the caller's `command` lists them.

    This does not look for controllers itself: which pads exist and which is
    player one is the business of whatever launched the session, and it says so
    by naming a command. None, or one that prints nothing usable, is no pads.
    """
    if not command:
        return ()
    return pads_from_json(_run(shlex.split(command), timeout=10))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config-dir", required=True, help="XDG config dir Dolphin uses (contains dolphin-emu/)")
    ap.add_argument("--gba", action="append", default=[], metavar="PORT=DEVICE", help="e.g. 1=sdl:Xbox 360 Controller, 2=keyboard, 3=pad:0")
    ap.add_argument("--pads-cmd", default=os.environ.get("SPLITSCREEN_PADS"),
                    help="a command printing the pads `pad:N` counts, as JSON (default: $SPLITSCREEN_PADS)")
    args = ap.parse_args(argv)

    # Only `pad:N` counts controllers. A caller that names its devices -- `sdl:`,
    # `keyboard` -- is not made to wait on an enumeration it has no use for.
    specs = [item.partition("=")[2] for item in args.gba]
    pads = detect_pads(args.pads_cmd) if any(spec.startswith("pad:") for spec in specs) else ()
    sections: dict[int, str] = {}
    for item in args.gba:
        port_s, _, spec = item.partition("=")
        try:
            port = int(port_s)
            device = parse_device(spec, pads, warn=lambda m: print(m, file=sys.stderr))
            sections[port] = gba_section(port, device)
        except ValueError as exc:
            print(f"dolphin_gba: {exc}", file=sys.stderr)
            return 2
        print(f"dolphin_gba: GBA{port} <- {device}")
    if not sections:
        print("dolphin_gba: nothing to do (no --gba given)", file=sys.stderr)
        return 2

    ini = Path(args.config_dir) / "dolphin-emu" / "GBA.ini"
    ini.parent.mkdir(parents=True, exist_ok=True)
    existing = ini.read_text() if ini.exists() else ""
    ini.write_text(rewrite(existing, sections))
    print(f"dolphin_gba: wrote {ini}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
