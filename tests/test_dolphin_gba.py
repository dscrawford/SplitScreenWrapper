import pytest
from splitscreen.handlers import dolphin_gba
from splitscreen.handlers.dolphin_gba import (KEYBOARD_DEVICE, clones_from_gotg, gba_section, rewrite,
                                              parse_device, pads_from_gotg, players_from_gotg)

GOTG_JSON = '[{"name": "Steam Controller", "slot": 0, "gamepad": true, "map": {}}, {"name": "Xbox 360 Controller", "slot": 1, "gamepad": true, "map": {}}, {"name": "Mouse", "slot": 2, "gamepad": false, "map": null}]'


def test_pads_from_gotg_keeps_gamepads_in_enumeration_order():
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


# gotg-pads' `slot` counts pads of the *same* identity, so two models both
# start at 0. Sorting by it interleaves them, and pad:2 stops meaning "the
# third controller" the moment somebody plugs in a second of anything.
INTERLEAVED = """[
  {"name": "Steam Controller", "slot": 0, "gamepad": true, "map": {}},
  {"name": "Xbox 360 Controller", "slot": 0, "gamepad": true, "map": {}},
  {"name": "Xbox 360 Controller", "slot": 1, "gamepad": true, "map": {}},
  {"name": "8BitDo Pro", "slot": 0, "gamepad": true, "map": {}}
]"""


def test_pads_are_not_reordered_by_their_per_model_slot():
    assert pads_from_gotg(INTERLEAVED) == (
        "SDL/0/Steam Controller",
        "SDL/0/Xbox 360 Controller",
        "SDL/1/Xbox 360 Controller",
        "SDL/0/8BitDo Pro",
    )


ORDER_JSON = """{
  "pinned": true, "ports": 4,
  "players": [
    {"player": 2, "seated": true, "name": "Xbox 360 Controller", "key": "0300abcd/1"},
    {"player": 1, "seated": true, "name": "Steam Controller", "key": "030028/0"},
    {"player": 3, "seated": false, "name": null, "key": null}
  ]
}"""


def test_players_from_gotg_is_player_order_not_json_order():
    # Player one first, whatever order the rows arrive in, and an empty seat is
    # not a controller somebody can be given.
    assert players_from_gotg(ORDER_JSON) == ("SDL/0/Steam Controller", "SDL/1/Xbox 360 Controller")


def test_players_from_gotg_survives_nonsense():
    assert players_from_gotg("not json") == ()
    assert players_from_gotg('{"players": "soon"}') == ()


def test_the_seating_a_person_chose_wins_over_enumeration(monkeypatch):
    # gotg seats pads by `gotg controllers order`; every emulator it launches
    # already uses that order, so a split screen must not invent its own.
    monkeypatch.setenv("GOTG_BIN", "/usr/bin/gotg")
    monkeypatch.setattr(dolphin_gba, "_run", lambda argv, timeout=20: ORDER_JSON if "controllers" in argv else INTERLEAVED)
    assert dolphin_gba.detect_pads()[0] == "SDL/0/Steam Controller"


def test_enumeration_is_the_fallback_when_gotg_cannot_answer(monkeypatch):
    monkeypatch.setenv("GOTG_BIN", "/usr/bin/gotg")
    monkeypatch.setenv("GOTG_PADS", "/usr/bin/gotg-pads")
    monkeypatch.setattr(dolphin_gba, "_run", lambda argv, timeout=20: "" if "controllers" in argv else INTERLEAVED)
    assert dolphin_gba.detect_pads() == pads_from_gotg(INTERLEAVED)


# --- padmap's clones, found by GUID ------------------------------------------
#
# Every GUID below was read off gotg-pads on a machine with two pads seated,
# 2026-09-21: an Xbox pad as player one and a pad SDL has never heard of as
# player two. SDL renamed the first clone and left the second alone, which is
# the whole reason this is matched on the GUID.

SEATED_JSON = """[
 {"name": "Xbox 360 Controller", "guid": "050018dc5e0400008e02000030110000",
  "slot": 0, "gamepad": true, "map": {}},
 {"name": "FSA Other Pad", "guid": "0300eee3aa2a0000bb5b000001000000",
  "slot": 0, "gamepad": true, "map": {}},
 {"name": "Xbox 360 Controller", "guid": "0300c9a75e0400008e02000001000000",
  "slot": 1, "gamepad": true, "map": {}},
 {"name": "padmap Player 2", "guid": "030089a6aa2a0000bb5b000002000000",
  "slot": 0, "gamepad": true, "map": {}}
]"""


def test_a_renamed_clone_is_still_found_by_its_guid():
    # Player one's clone mirrors an Xbox pad, so SDL calls it "Xbox 360
    # Controller" and the kernel's "padmap Player 1" never reaches Dolphin.
    clones = clones_from_gotg(SEATED_JSON)
    assert clones[1] == "SDL/1/Xbox 360 Controller"


def test_a_clone_sdl_left_alone_is_found_too():
    assert clones_from_gotg(SEATED_JSON)[2] == "SDL/0/padmap Player 2"


def test_the_pads_behind_the_clones_are_not_mistaken_for_them():
    # The raw Xbox pad enumerates first and is named identically to its own
    # clone; only the GUID tells them apart.
    clones = clones_from_gotg(SEATED_JSON)
    assert "SDL/0/Xbox 360 Controller" not in clones.values()
    assert set(clones) == {1, 2}


def test_padmap_specs_resolve_to_those_devices():
    clones = clones_from_gotg(SEATED_JSON)
    assert parse_device("padmap:1", (), clones=clones) == "SDL/1/Xbox 360 Controller"
    assert parse_device("padmap:2", (), clones=clones) == "SDL/0/padmap Player 2"


def test_a_player_padmap_never_published_falls_back_to_the_keyboard():
    said = []
    assert parse_device("padmap:3", (), warn=said.append, clones=clones_from_gotg(SEATED_JSON)) == KEYBOARD_DEVICE
    assert said and "player 3" in said[0]


def test_nothing_published_at_all_is_not_a_crash():
    assert clones_from_gotg("not json") == {}
    assert parse_device("padmap:1", (), warn=lambda _m: None, clones={}) == KEYBOARD_DEVICE


def test_a_bad_player_number_is_refused():
    import pytest

    with pytest.raises(ValueError):
        parse_device("padmap:one", ())
    with pytest.raises(ValueError):
        parse_device("danstick:one", ())


# --- danstick, as padmap is now called ----------------------------------------
#
# The same seating after the rename (2026-09): the clones are "danstick Player
# N", and GOTG asks for them as `danstick:N`. Four Swords Adventures stopped
# launching when GOTG changed its spec and this did not.

RENAMED_JSON = SEATED_JSON.replace("padmap Player 2", "danstick Player 2").replace(
    "0300c9a7", "0300{:02x}{:02x}".format(*dolphin_gba._crc16(b"danstick Player 1").to_bytes(2, "little"))
).replace(
    "030089a6", "0300{:02x}{:02x}".format(*dolphin_gba._crc16(b"danstick Player 2").to_bytes(2, "little"))
)


def test_danstick_specs_resolve_to_danstick_clones():
    clones = clones_from_gotg(RENAMED_JSON)
    assert parse_device("danstick:1", (), clones=clones) == "SDL/1/Xbox 360 Controller"
    assert parse_device("danstick:2", (), clones=clones) == "SDL/0/danstick Player 2"
    assert parse_device("padmap:1", (), clones=clones) == "SDL/1/Xbox 360 Controller", "the old spec still works"


def test_a_danstick_player_never_published_is_the_keyboard_and_says_so():
    said = []
    assert parse_device("danstick:3", (), warn=said.append, clones={}) == KEYBOARD_DEVICE
    assert said and "danstick" in said[0]
