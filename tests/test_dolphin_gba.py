import pytest
from splitscreen.handlers.dolphin_gba import (KEYBOARD_DEVICE, gba_section, rewrite, parse_device, pads_from_gotg)

GOTG_JSON = '[{"name": "Steam Controller", "slot": 0, "gamepad": true, "map": {}}, {"name": "Xbox 360 Controller", "slot": 1, "gamepad": true, "map": {}}, {"name": "Mouse", "slot": 2, "gamepad": false, "map": null}]'


def test_pads_from_gotg_keeps_gamepads_in_slot_order():
    assert pads_from_gotg(GOTG_JSON) == ("SDL/0/Steam Controller", "SDL/1/Xbox 360 Controller")
    assert pads_from_gotg("not json") == ()


def test_parse_device_forms():
    pads = ("SDL/0/Steam Controller",)
    assert parse_device("pad:0", pads) == "SDL/0/Steam Controller"
    assert parse_device("sdl:Foo Pad", pads) == "SDL/0/Foo Pad"
    assert parse_device("keyboard", pads) == KEYBOARD_DEVICE
    with pytest.raises(ValueError):
        parse_device("usb:1", pads)


def test_missing_pad_falls_back_to_keyboard_with_warning():
    warnings = []
    assert parse_device("pad:1", ("SDL/0/Steam Controller",), warn=warnings.append) == KEYBOARD_DEVICE
    assert warnings and "pad:1" in warnings[0]


def test_section_uses_pad_map_or_keyboard_map():
    pad = gba_section(1, "SDL/0/Steam Controller")
    assert pad.startswith("[GBA1]\nDevice = SDL/0/Steam Controller\n") and "Buttons/A = `Button S`" in pad
    kb = gba_section(2, KEYBOARD_DEVICE)
    assert "Buttons/A = `X`" in kb
    with pytest.raises(ValueError):
        gba_section(5, "x")


def test_rewrite_replaces_only_named_ports_and_keeps_rest():
    existing = "[GBA1]\nDevice = old\nButtons/A = `Z`\n[GBA2]\nDevice = old2\n[Other]\nKey = 1\n"
    out = rewrite(existing, {1: gba_section(1, "SDL/0/Pad")})
    assert "Device = old\n" not in out
    assert "[GBA2]\nDevice = old2\n" in out and "[Other]\nKey = 1\n" in out
    assert out.count("[GBA1]") == 1 and "Device = SDL/0/Pad" in out


def test_rewrite_on_empty_file():
    out = rewrite("", {1: gba_section(1, "SDL/0/Pad"), 2: gba_section(2, KEYBOARD_DEVICE)})
    assert out.index("[GBA1]") < out.index("[GBA2]")


def test_gotg_pads_path_is_read_from_wrapper(tmp_path):
    from splitscreen.handlers.dolphin_gba import gotg_pads_from_wrapper
    store = tmp_path / "nix/store/abc-gotg-pads-0.1.0/bin"
    store.mkdir(parents=True)
    (store / "gotg-pads").write_text("#!/bin/sh\n")
    wrapper = tmp_path / "gotg"
    wrapper.write_text(f"PATH='{store}'$PATH\n")
    assert gotg_pads_from_wrapper(wrapper) == str(store / "gotg-pads")
    assert gotg_pads_from_wrapper(tmp_path / "missing") is None
