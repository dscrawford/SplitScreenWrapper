"""Four Swords Adventures mode.

The whole point of the mode is that four things agree: where a player's GBA
window goes, which window rule catches it, which Dolphin port becomes a GBA,
and which controller drives it. Every test here is about one of those four
lining up with the other three, because a session where player 3's screen is in
the corner and player 3's controller drives GBA2 is not obviously broken — it
is just wrong, and only once four people are holding pads.
"""
import json

import pytest

from splitscreen import layout
from splitscreen.config import session_from_dict
from splitscreen.modes import expand as expand_config
from splitscreen.modes import fsa

BASE = {"name": "fsa", "gc": "usa.legend_of_zelda_four_swords_adventures", "gba_bios": "/roms/gba_bios.bin"}


def config(**extra) -> dict:
    return fsa.expand({**BASE, **extra})


def rects(players: int, width: int = 1920, height: int = 1080):
    slots = config(players=players)["layout"]["slots"]
    return layout.compute("free", len(slots), width, height, slots=slots)


# --- where the windows go ---------------------------------------------------


def test_one_player_has_the_frame_to_themselves():
    # No GBA is used at all, so there is nothing to put beside the game.
    assert rects(1) == (layout.Rect(0, 0, 1920, 1080),)
    assert config(players=1)["instances"][0].get("windows") is None


def test_two_players_stack_both_gbas_down_the_left():
    gba1, gba2, game = rects(2)
    assert (gba1.x, gba1.y) == (0, 0) and (gba2.x, gba2.y) == (0, 540)
    assert gba1.w == gba2.w and gba1.h == gba2.h == 540
    # The game takes everything the column does not.
    assert (game.x, game.w) == (gba1.w, 1920 - gba1.w) and game.h == 1080


def test_four_players_put_two_down_each_side_with_the_game_between():
    gba1, gba2, gba3, gba4, game = rects(4)
    assert (gba1.x, gba1.y) == (0, 0) and (gba2.x, gba2.y) == (0, 540)
    assert gba3.x == gba4.x == 1920 - gba1.w and (gba3.y, gba4.y) == (0, 540)
    assert game.x == gba1.w and game.x + game.w == gba3.x


def test_three_players_leave_the_fourth_corner_blank():
    three = rects(3)
    four = rects(4)
    assert len(three) == 4, "three GBAs and the game"
    # Player 3 sits exactly where they would with four players, so somebody
    # joining moves nobody who is already playing.
    assert three[2] == four[2]
    assert three[3] == four[4], "and the game keeps the same middle"


def test_the_slots_never_overlap():
    for players in (1, 2, 3, 4):
        found = rects(players)
        for i, a in enumerate(found):
            for b in found[i + 1:]:
                apart = a.x + a.w <= b.x or b.x + b.w <= a.x or a.y + a.h <= b.y or b.y + b.h <= a.y
                assert apart, f"{players} players: {a} overlaps {b}"


def test_the_side_columns_can_be_resized():
    narrow = layout.compute("free", 3, 1000, 1000, slots=config(players=2, side_fraction=0.1)["layout"]["slots"])
    assert narrow[0].w == 100 and narrow[2].w == 900


# --- the windows, the ports and the controllers, in the same order ----------


def test_window_rules_run_gba1_upwards_then_the_game():
    rules = config(players=4)["instances"][0]["windows"]
    assert [w["id"] for w in rules] == ["gba1", "gba2", "gba3", "gba4", "main"]
    assert [w["match"] for w in rules][:4] == [r"^GBA1\b", r"^GBA2\b", r"^GBA3\b", r"^GBA4\b"]


def test_a_port_becomes_a_gba_for_every_player_and_no_more():
    command = config(players=3)["instances"][0]["command"]
    assert "Dolphin.Core.SIDevice0=13" in command
    assert "Dolphin.Core.SIDevice1=13" in command
    assert "Dolphin.Core.SIDevice2=13" in command
    assert not any(c.startswith("Dolphin.Core.SIDevice3") for c in command), "a fourth port nobody is holding"


def test_one_player_gets_a_controller_rather_than_a_gba():
    command = config(players=1)["instances"][0]["command"]
    assert "Dolphin.Core.SIDevice0=6" in command
    assert not any("=13" in c for c in command)


def test_controllers_are_handed_out_in_order():
    pre = config(players=4)["instances"][0]["pre_launch"]
    assert len(pre) == 1, "one command, so the ports are written together or not at all"
    pairs = [pre[0][i + 1] for i, arg in enumerate(pre[0]) if arg == "--gba"]
    assert pairs == ["1=pad:0", "2=pad:1", "3=pad:2", "4=pad:3"]


def test_the_order_can_be_overridden_per_player():
    # Two pads that enumerate the wrong way round, and a keyboard in seat three.
    pre = config(players=3, pads=["pad:1", "pad:0", "keyboard"])["instances"][0]["pre_launch"][0]
    pairs = [pre[i + 1] for i, arg in enumerate(pre) if arg == "--gba"]
    assert pairs == ["1=pad:1", "2=pad:0", "3=keyboard"]


def test_a_partial_list_of_pads_is_refused():
    # Silently filling the rest in would hand somebody another player's pad.
    with pytest.raises(ValueError):
        config(players=3, pads=["pad:0", "pad:1"])


def test_one_player_binds_nothing():
    assert "pre_launch" not in config(players=1)["instances"][0]


def test_the_binding_and_the_windows_agree_on_how_many_players_there_are():
    for players in (2, 3, 4):
        made = config(players=players)["instances"][0]
        bound = [a for a in made["pre_launch"][0] if a == "--gba"]
        assert len(bound) == players == len(made["windows"]) - 1


# --- the two sources --------------------------------------------------------


def test_an_entry_id_is_launched_through_gotg():
    made = config(players=2)["instances"][0]
    assert made["command"][1:3] == ["play", BASE["gc"]]
    # A fullscreen Dolphin would cover the GBAs it is supposed to sit between.
    assert made["env"]["GOTG_FULLSCREEN"] == "0"
    assert "Dolphin.Display.Fullscreen=False" in made["command"]


def test_a_disc_path_is_launched_through_dolphin():
    made = fsa.expand({**BASE, "gc": "/games/fsa.iso", "players": 2})["instances"][0]
    assert made["command"][:4] == ["dolphin-emu", "-b", "-e", "/games/fsa.iso"]
    assert "env" not in made, "nothing to tell a plain Dolphin about gotg"


def test_the_gba_bios_is_passed_to_dolphin():
    assert f"Dolphin.GBA.BIOS={BASE['gba_bios']}" in config(players=2)["instances"][0]["command"]


def test_both_sources_are_required():
    with pytest.raises(ValueError, match="gc"):
        fsa.expand({"name": "fsa", "players": 2, "gba_bios": "/roms/gba_bios.bin"})
    with pytest.raises(ValueError, match="gba_bios"):
        fsa.expand({"name": "fsa", "players": 2, "gc": "usa.x"})


@pytest.mark.parametrize("players", [0, 5, -1, "2", 2.0, True])
def test_only_one_to_four_can_play(players):
    with pytest.raises(ValueError):
        config(players=players)


# --- as a config ------------------------------------------------------------


def test_a_mode_becomes_a_session_whose_slots_match_its_windows():
    session = session_from_dict({"frame": {"width": 1920, "height": 1080},
                                 "mode": {**BASE, "players": 3}})
    slot_ids = [w.id for i in session.instances for w in i.window_specs]
    assert slot_ids == ["gba1", "gba2", "gba3", "main"]
    assert len(session.layout_args["slots"]) == len(slot_ids)
    assert layout.compute(session.layout, len(slot_ids), 1920, 1080, **session.layout_args)


def test_a_config_may_overrule_what_the_mode_wrote():
    session = session_from_dict({"mode": {**BASE, "players": 2}, "layout": {"name": "grid"}})
    assert session.layout == "grid", "hand-tuning beats the mode"
    assert [w.id for w in session.instances[0].window_specs] == ["gba1", "gba2", "main"]


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError, match="unknown mode"):
        session_from_dict({"mode": {"name": "smash"}, "instances": [{"id": "a", "command": ["x"]}]})


def test_a_config_without_a_mode_is_untouched():
    plain = {"instances": [{"id": "a", "command": ["x"]}]}
    assert expand_config(plain) == plain


def test_a_pinned_dolphin_can_be_named(tmp_path):
    # A launcher that builds its own Dolphin — gotg does — must be able to say
    # which one, rather than hoping PATH agrees with it.
    out = tmp_path / "fsa.json"
    fsa.main(["--players", "2", "--gc", "/games/fsa.rvz", "--gba-bios", BASE["gba_bios"],
              "--dolphin", "/nix/store/abc-dolphin/bin/dolphin-emu", "-o", str(out)])
    assert json.loads(out.read_text())["instances"][0]["command"][0] == "/nix/store/abc-dolphin/bin/dolphin-emu"


def test_the_command_line_writes_the_same_config(tmp_path, capsys):
    out = tmp_path / "fsa.json"
    assert fsa.main(["--players", "4", "--gc", BASE["gc"], "--gba-bios", BASE["gba_bios"], "-o", str(out)]) == 0
    written = json.loads(out.read_text())
    # No frame unless one is asked for: the session sizes it to the screen.
    assert "frame" not in written
    assert written["instances"] == config(players=4)["instances"]
    session_from_dict(written)  # and it is a config the session accepts


def test_a_frame_size_given_on_the_command_line_is_kept(tmp_path):
    out = tmp_path / "fsa.json"
    assert fsa.main(["--players", "2", "--gc", BASE["gc"], "--gba-bios", BASE["gba_bios"],
                     "--width", "1280", "--height", "800", "-o", str(out)]) == 0
    assert json.loads(out.read_text())["frame"] == {"width": 1280, "height": 800}
