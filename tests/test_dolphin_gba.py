import pytest
from splitscreen.handlers import dolphin_gba
from splitscreen.handlers.dolphin_gba import KEYBOARD_DEVICE, gba_section, pads_from_json, parse_device, rewrite

PADS_JSON = '[{"name": "Steam Controller", "slot": 0, "gamepad": true, "map": {}}, {"name": "Xbox 360 Controller", "slot": 1, "gamepad": true, "map": {}}, {"name": "Mouse", "slot": 2, "gamepad": false, "map": null}]'


def test_a_pad_list_keeps_gamepads_in_its_own_order():
    assert pads_from_json(PADS_JSON) == ("SDL/0/Steam Controller", "SDL/1/Xbox 360 Controller")
    assert pads_from_json("not json") == ()


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


INTERLEAVED = """[
  {"name": "Steam Controller", "slot": 0, "gamepad": true, "map": {}},
  {"name": "Xbox 360 Controller", "slot": 0, "gamepad": true, "map": {}},
  {"name": "Xbox 360 Controller", "slot": 1, "gamepad": true, "map": {}},
  {"name": "8BitDo Pro", "slot": 0, "gamepad": true, "map": {}}
]"""


def test_pads_are_not_reordered_by_their_per_model_slot():
    assert pads_from_json(INTERLEAVED) == (
        "SDL/0/Steam Controller",
        "SDL/0/Xbox 360 Controller",
        "SDL/1/Xbox 360 Controller",
        "SDL/0/8BitDo Pro",
    )


def test_pad_n_counts_the_callers_list_in_the_callers_order(monkeypatch):
    # Which pad is player one is the launcher's to say; the list it prints is
    # taken in the order it is printed.
    seen = []
    monkeypatch.setattr(dolphin_gba, "_run", lambda argv, timeout=20: seen.append(argv) or INTERLEAVED)
    assert dolphin_gba.detect_pads("my-pads --json") == pads_from_json(INTERLEAVED)
    assert seen == [["my-pads", "--json"]]


def test_no_pad_command_is_no_pads_and_the_warning_says_why():
    assert dolphin_gba.detect_pads(None) == ()
    said = []
    assert parse_device("pad:0", (), warn=said.append) == KEYBOARD_DEVICE
    assert "--pads-cmd" in said[0]


def test_a_pad_list_that_is_not_one_is_no_pads():
    assert pads_from_json('{"players": []}') == ()
    assert pads_from_json('[{"slot": 0}, "x"]') == ()


def test_named_devices_do_not_wait_on_an_enumeration(monkeypatch, tmp_path):
    def refuse(_command):
        raise AssertionError("pads were enumerated for sdl:/keyboard specs")

    monkeypatch.setattr(dolphin_gba, "detect_pads", refuse)
    assert dolphin_gba.main(
        ["--config-dir", str(tmp_path), "--gba", "1=sdl:Some Pad 1", "--gba", "2=keyboard"]
    ) == 0
    ini = (tmp_path / "dolphin-emu" / "GBA.ini").read_text()
    assert "SDL/0/Some Pad 1" in ini


def test_a_pad_index_still_enumerates(monkeypatch, tmp_path):
    asked = []
    monkeypatch.setattr(dolphin_gba, "detect_pads", lambda command: asked.append(command) or ("SDL/0/Pad A",))
    assert dolphin_gba.main(["--config-dir", str(tmp_path), "--pads-cmd", "my-pads", "--gba", "1=pad:0"]) == 0
    assert asked == ["my-pads"]
    assert "SDL/0/Pad A" in (tmp_path / "dolphin-emu" / "GBA.ini").read_text()
