"""Which backend the nested sway nests in.

A Steam Deck in Game Mode is gamescope: games are X11 windows to it, and the
Wayland it exposes is not something wlroots can nest a compositor in. Forcing
`WLR_BACKENDS=wayland` there was a sway that never came up.
"""

from splitscreen.session import nested_backends


def test_a_wayland_desktop_nests_in_wayland_first_and_can_fall_back_to_x11():
    assert nested_backends({"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ":0"}) == ["wayland", "x11"]


def test_gamescope_with_only_an_x_display_is_x11():
    assert nested_backends({"DISPLAY": ":1"}) == ["x11"]


def test_wayland_alone_is_wayland():
    assert nested_backends({"WAYLAND_DISPLAY": "wayland-0"}) == ["wayland"]


def test_empty_values_do_not_count():
    assert nested_backends({"WAYLAND_DISPLAY": "", "DISPLAY": ":0"}) == ["x11"]


def test_nothing_set_still_tries_wayland_so_the_error_names_the_log():
    assert nested_backends({}) == ["wayland"]
