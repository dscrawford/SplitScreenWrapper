"""End-to-end: virtual keyboard -> kbd2pad.forward -> virtual gamepad.

Needs /dev/uinput write access (input group). Skipped otherwise. No real
hardware is touched: the "keyboard" is itself a uinput device.
"""
import os
import select
import threading

import pytest
from evdev import InputDevice, UInput, ecodes as e, list_devices

from splitscreen.kbd2pad import make_pad, forward, AXIS_MAX

pytestmark = pytest.mark.skipif(not os.access("/dev/uinput", os.W_OK), reason="no /dev/uinput access")


def _find(name: str) -> InputDevice:
    for _ in range(50):
        for p in list_devices():
            d = InputDevice(p)
            if d.name == name:
                return d
            d.close()
        select.select([], [], [], 0.05)
    raise AssertionError(f"device {name!r} never appeared")


def _drain(dev: InputDevice, timeout: float = 1.0) -> list:
    got = []
    while select.select([dev.fd], [], [], timeout)[0]:
        got.extend(dev.read())
        timeout = 0.2
    return got


def test_keyboard_events_become_gamepad_events():
    fake_kbd = UInput({e.EV_KEY: [e.KEY_D, e.KEY_W, e.KEY_J]}, name="splitscreen-test-kbd")
    kbd_reader = _find("splitscreen-test-kbd")
    pad = make_pad("splitscreen-test-pad")
    pad_reader = _find("splitscreen-test-pad")
    t = threading.Thread(target=forward, args=(kbd_reader, pad), daemon=True)
    t.start()
    try:
        fake_kbd.write(e.EV_KEY, e.KEY_D, 1); fake_kbd.syn()
        fake_kbd.write(e.EV_KEY, e.KEY_J, 1); fake_kbd.syn()
        fake_kbd.write(e.EV_KEY, e.KEY_D, 0); fake_kbd.syn()
        evs = [(ev.type, ev.code, ev.value) for ev in _drain(pad_reader)]
        assert (e.EV_ABS, e.ABS_X, AXIS_MAX) in evs
        assert (e.EV_ABS, e.ABS_HAT0X, 1) in evs
        assert (e.EV_KEY, e.BTN_SOUTH, 1) in evs
        assert (e.EV_ABS, e.ABS_X, 0) in evs
        # the pad advertises itself as an Xbox 360 controller so SDL maps it without config
        assert (pad_reader.info.vendor, pad_reader.info.product) == (0x045E, 0x028E)
    finally:
        pad_reader.close()
        fake_kbd.close()
