"""The frame follows the screen.

1920x1080 written into a config is 1920x1080 on a Steam Deck's 1280x800 panel:
a nested compositor hanging off the edge with a Game Boy past the bezel.
"""

from splitscreen import screen

DECK_DESKTOP = """Screen 0: minimum 320 x 200, current 1280 x 800, maximum 16384 x 16384
eDP connected primary 1280x800+0+0 (normal left inverted right x axis y axis) 0mm x 0mm
   1280x800      60.00*+   59.99
   1024x768      59.99
"""

TWO_MONITORS = """Screen 0: minimum 320 x 200, current 4480 x 1440, maximum 16384 x 16384
DP-1 connected primary 2560x1440+0+0 (normal left inverted right x axis y axis) 597mm x 336mm
   2560x1440     59.95*+
DP-2 connected 1920x1080+2560+0 (normal left inverted right x axis y axis) 527mm x 296mm
   1920x1080     60.00 +
"""

GAMESCOPE_NO_MODES = """Screen 0: minimum 16 x 16, current 1280 x 800, maximum 32767 x 32767
XWAYLAND0 connected 1280x800+0+0 0mm x 0mm
"""

# The Deck's own panel under KDE's Xwayland, verbatim: a portrait panel shown
# rotated, so the mode says 800x1280 and the screen is 1280x800.
DECK_ROTATED = """Screen 0: minimum 16 x 16, current 1280 x 800, maximum 32767 x 32767
eDP-1 connected primary 1280x800+0+0 right (normal left inverted right x axis y axis) 100mm x 160mm
   800x1280      89.87*+
   800x600       89.85  
"""

# No geometry on any output: only the virtual size is left to go by.
NO_GEOMETRY = """Screen 0: minimum 16 x 16, current 1920 x 1080, maximum 32767 x 32767
default connected (normal left inverted right x axis y axis) 0mm x 0mm
"""


def test_the_deck_panel_is_read_off_its_geometry():
    assert screen.parse_xrandr(DECK_DESKTOP) == (1280, 800)


def test_a_rotated_panel_is_its_size_on_the_screen_not_its_mode():
    # Measured on a Deck: the frame came up 800x1280, on its side.
    assert screen.parse_xrandr(DECK_ROTATED) == (1280, 800)


def test_an_output_with_no_geometry_falls_back_to_the_virtual_size():
    assert screen.parse_xrandr(NO_GEOMETRY) == (1920, 1080)


def test_two_monitors_give_the_one_in_use_not_the_desktop_spanning_both():
    assert screen.parse_xrandr(TWO_MONITORS) == (2560, 1440)


def test_gamescope_with_no_mode_list_is_read_off_its_output():
    assert screen.parse_xrandr(GAMESCOPE_NO_MODES) == (1280, 800)


def test_nothing_readable_is_none():
    assert screen.parse_xrandr("xrandr: Failed to get size of gamma for output default") is None
    assert screen.parse_xrandr("") is None


def test_no_display_and_no_sway_means_nobody_can_say():
    assert screen.host_screen_size({}) is None


def test_the_session_takes_the_screen_when_the_config_names_no_frame(monkeypatch):
    from splitscreen import session as session_mod

    monkeypatch.setattr(screen, "host_screen_size", lambda environ=None: (1280, 800))
    seen = {}

    def fake_start(workdir, width, height):
        seen["size"] = (width, height)
        raise RuntimeError("stop here")

    monkeypatch.setattr(session_mod, "start_nested_sway", fake_start)
    from splitscreen.config import Session

    runner = session_mod.Runner(Session(instances=()), workdir=__import__("pathlib").Path("/tmp"))
    try:
        runner.run()
    except RuntimeError:
        pass
    assert seen["size"] == (1280, 800)


def test_a_frame_the_config_names_wins_over_the_screen(monkeypatch):
    from splitscreen import session as session_mod

    monkeypatch.setattr(screen, "host_screen_size", lambda environ=None: (1280, 800))
    seen = {}

    def fake_start(workdir, width, height):
        seen["size"] = (width, height)
        raise RuntimeError("stop here")

    monkeypatch.setattr(session_mod, "start_nested_sway", fake_start)
    from splitscreen.config import Session

    runner = session_mod.Runner(Session(instances=(), width=1920, height=1080), workdir=__import__("pathlib").Path("/tmp"))
    try:
        runner.run()
    except RuntimeError:
        pass
    assert seen["size"] == (1920, 1080)
