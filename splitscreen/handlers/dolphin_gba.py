"""Bind controllers to Dolphin's integrated GBA ports (GBA.ini).

Dolphin keeps GBA bindings in <config>/dolphin-emu/GBA.ini, one [GBAn] section
per port, and reads it at startup. Nothing on the command line can set it, so
this runs as a `pre_launch` step of a split-screen instance:

    python3 -m splitscreen.handlers.dolphin_gba --config-dir ~/.local/state/gotg/env/env-gamecube/config \\
        --gba 1=pad:0 --gba 2=pad:1

Device forms: `pad:N` = Nth controller reported by gotg-pads (or SDL order),
`sdl:<Name>` = "SDL/0/<Name>" verbatim, `keyboard` = Dolphin's stock key map.
A `pad:N` that is not plugged in falls back to the keyboard with a warning, so
a missing second controller never blocks the launch.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
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
        warn(f"dolphin_gba: pad:{idx} is not connected ({len(pads)} pad(s) found); using keyboard")
        return KEYBOARD_DEVICE
    raise ValueError(f"unknown device spec {spec!r}; use pad:N, sdl:<name> or keyboard")


def pads_from_gotg(output: str) -> tuple[str, ...]:
    """Pure: gotg-pads JSON -> Dolphin device strings, in gotg's slot order."""
    try:
        rows = json.loads(output)
    except ValueError:
        return ()
    rows = [r for r in rows if isinstance(r, dict) and r.get("gamepad") and r.get("map") is not None]
    rows.sort(key=lambda r: int(r.get("slot", 0)))
    return tuple(f"SDL/{int(r.get('slot', 0))}/{r.get('name', 'Unknown')}" for r in rows)


def gotg_pads_from_wrapper(wrapper: Path = Path.home() / ".local/state/gotg/app/bin/gotg") -> str | None:
    """gotg keeps gotg-pads off PATH and reaches it through its own wrapper's PATH edits;
    pull the store path out of that wrapper so the handler works without configuration."""
    try:
        m = re.search(r"([^':\s]*gotg-pads[^':\s]*/bin)", wrapper.read_text())
    except OSError:
        return None
    if not m:
        return None
    exe = Path(m.group(1)) / "gotg-pads"
    return str(exe) if exe.exists() else None


def detect_pads() -> tuple[str, ...]:
    exe = os.environ.get("GOTG_PADS") or shutil.which("gotg-pads") or gotg_pads_from_wrapper()
    if not exe:
        return ()
    try:
        out = subprocess.run([exe], capture_output=True, text=True, timeout=10, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return ()
    return pads_from_gotg(out)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config-dir", required=True, help="XDG config dir Dolphin uses (contains dolphin-emu/)")
    ap.add_argument("--gba", action="append", default=[], metavar="PORT=DEVICE", help="e.g. 1=pad:0, 2=keyboard, 3=sdl:Xbox 360 Controller")
    ap.add_argument("--pads-bin", help="override gotg-pads binary (default: $GOTG_PADS or PATH)")
    args = ap.parse_args(argv)
    if args.pads_bin:
        os.environ["GOTG_PADS"] = args.pads_bin

    pads = detect_pads()
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
