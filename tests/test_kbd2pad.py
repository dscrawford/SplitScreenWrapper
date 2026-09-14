from evdev import ecodes as e
from splitscreen.kbd2pad import axis_state, DEFAULT_MAP, AXIS_MAX


def test_no_keys_is_centered():
    assert axis_state(frozenset(), DEFAULT_MAP) == (0, 0)


def test_single_directions():
    assert axis_state(frozenset({e.KEY_D}), DEFAULT_MAP) == (AXIS_MAX, 0)
    assert axis_state(frozenset({e.KEY_UP}), DEFAULT_MAP) == (0, -AXIS_MAX)


def test_opposites_cancel_and_diagonals_combine():
    assert axis_state(frozenset({e.KEY_A, e.KEY_D}), DEFAULT_MAP) == (0, 0)
    assert axis_state(frozenset({e.KEY_W, e.KEY_D}), DEFAULT_MAP) == (AXIS_MAX, -AXIS_MAX)


def test_wasd_and_arrows_saturate_not_overflow():
    assert axis_state(frozenset({e.KEY_D, e.KEY_RIGHT}), DEFAULT_MAP) == (AXIS_MAX, 0)


def test_buttons_do_not_move_axes():
    assert axis_state(frozenset({e.KEY_J, e.KEY_ENTER}), DEFAULT_MAP) == (0, 0)
