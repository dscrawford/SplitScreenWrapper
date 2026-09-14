"""Turn one physical keyboard into a virtual Xbox-style gamepad.

The keyboard is grabbed (EVIOCGRAB) so the desktop compositor no longer sees
it, and a uinput gamepad is created that any game recognises via SDL's
built-in Xbox 360 mapping. Combined with bubblewrap masking, this gives one
keyboard per player for games that only know about gamepads, without any
per-game configuration.

    python3 -m splitscreen.kbd2pad --device /dev/input/by-id/...-event-kbd

Prints the created device node on stdout, then forwards until SIGTERM.
Requires read access to the keyboard and write access to /dev/uinput
(the `input` group on most distros).
"""
from __future__ import annotations

import argparse
import signal
import sys
from collections.abc import Mapping

from evdev import AbsInfo, InputDevice, UInput, ecodes as e

AXIS_MAX = 32767

DEFAULT_MAP: Mapping[int, tuple[str, int]] = {
    e.KEY_W: ("axis", -1), e.KEY_UP: ("axis", -1),
    e.KEY_S: ("axis", +1), e.KEY_DOWN: ("axis", +1),
    e.KEY_A: ("axis", -2), e.KEY_LEFT: ("axis", -2),
    e.KEY_D: ("axis", +2), e.KEY_RIGHT: ("axis", +2),
    e.KEY_J: ("btn", e.BTN_SOUTH), e.KEY_Z: ("btn", e.BTN_SOUTH), e.KEY_SPACE: ("btn", e.BTN_SOUTH),
    e.KEY_K: ("btn", e.BTN_EAST), e.KEY_X: ("btn", e.BTN_EAST),
    e.KEY_U: ("btn", e.BTN_WEST), e.KEY_C: ("btn", e.BTN_WEST),
    e.KEY_I: ("btn", e.BTN_NORTH), e.KEY_V: ("btn", e.BTN_NORTH),
    e.KEY_Q: ("btn", e.BTN_TL), e.KEY_E: ("btn", e.BTN_TR),
    e.KEY_ENTER: ("btn", e.BTN_START), e.KEY_BACKSPACE: ("btn", e.BTN_SELECT),
    e.KEY_TAB: ("btn", e.BTN_MODE),
}


def make_pad(name: str) -> UInput:
    absinfo = AbsInfo(value=0, min=-AXIS_MAX, max=AXIS_MAX, fuzz=16, flat=128, resolution=0)
    caps = {
        e.EV_KEY: [e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_TL, e.BTN_TR,
                   e.BTN_SELECT, e.BTN_START, e.BTN_MODE, e.BTN_THUMBL, e.BTN_THUMBR],
        e.EV_ABS: [(e.ABS_X, absinfo), (e.ABS_Y, absinfo), (e.ABS_RX, absinfo), (e.ABS_RY, absinfo),
                   (e.ABS_HAT0X, AbsInfo(0, -1, 1, 0, 0, 0)), (e.ABS_HAT0Y, AbsInfo(0, -1, 1, 0, 0, 0))],
    }
    # Xbox 360 vendor/product so SDL/Steam apply their stock mapping without a gamecontrollerdb entry.
    return UInput(caps, name=name, vendor=0x045E, product=0x028E, version=0x110, bustype=e.BUS_USB)


def axis_state(held: frozenset[int], mapping: Mapping[int, tuple[str, int]]) -> tuple[int, int]:
    """Pure: derive (x, y) stick values from the set of held keys."""
    x = y = 0
    for key in held:
        kind, val = mapping.get(key, ("", 0))
        if kind != "axis":
            continue
        if abs(val) == 1:
            y += AXIS_MAX * (1 if val > 0 else -1)
        else:
            x += AXIS_MAX * (1 if val > 0 else -1)
    return max(-AXIS_MAX, min(AXIS_MAX, x)), max(-AXIS_MAX, min(AXIS_MAX, y))


def forward(kbd: InputDevice, pad: UInput, mapping: Mapping[int, tuple[str, int]] = DEFAULT_MAP) -> None:
    held: frozenset[int] = frozenset()
    for ev in kbd.read_loop():
        if ev.type != e.EV_KEY or ev.value == 2:  # ignore autorepeat
            continue
        held = held | {ev.code} if ev.value else held - {ev.code}
        kind, val = mapping.get(ev.code, ("", 0))
        if kind == "btn":
            pad.write(e.EV_KEY, val, ev.value)
        elif kind == "axis":
            x, y = axis_state(held, mapping)
            pad.write(e.EV_ABS, e.ABS_X, x)
            pad.write(e.EV_ABS, e.ABS_Y, y)
            pad.write(e.EV_ABS, e.ABS_HAT0X, (x > 0) - (x < 0))
            pad.write(e.EV_ABS, e.ABS_HAT0Y, (y > 0) - (y < 0))
        else:
            continue
        pad.syn()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", required=True, help="/dev/input/eventN or by-id path of the keyboard")
    ap.add_argument("--name", default="Split Screen Virtual Pad")
    ap.add_argument("--no-grab", action="store_true", help="do not take exclusive ownership of the keyboard")
    args = ap.parse_args(argv)

    try:
        kbd = InputDevice(args.device)
    except OSError as exc:
        print(f"kbd2pad: cannot open {args.device}: {exc}", file=sys.stderr)
        return 2
    try:
        pad = make_pad(args.name)
    except OSError as exc:
        print(f"kbd2pad: cannot create uinput device (need write access to /dev/uinput): {exc}", file=sys.stderr)
        kbd.close()
        return 2
    if not args.no_grab:
        try:
            kbd.grab()
        except OSError as exc:
            print(f"kbd2pad: cannot grab {args.device} (already grabbed?): {exc}", file=sys.stderr)
            pad.close()
            kbd.close()
            return 2
    print(pad.device.path, flush=True)

    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        forward(kbd, pad)
    except KeyboardInterrupt:
        pass
    finally:
        if not args.no_grab:
            try:
                kbd.ungrab()
            except OSError:
                pass
        pad.close()
        kbd.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
