"""A game that fullscreens or resizes itself is put back in its slot.

Every instance keeps its own video options, and using them used to end the
split screen: "fullscreen" gave one player the whole frame and hid everyone
else behind it, and a resolution change left the window its own size, centred
over its neighbours. The placement was only re-asserted for the first few
seconds of a window's life, and never undid fullscreen at all.
"""
from pathlib import Path
from types import SimpleNamespace

from splitscreen import session as session_mod
from splitscreen.config import session_from_dict
from splitscreen.layout import Rect
from splitscreen.session import NESTED_CONFIG, Runner, matches

SLOT = Rect(0, 0, 100, 100)


class FakeCon:
    def __init__(self, con_id=1, pid=1001, rect=SLOT, fullscreen_mode=0, name=None):
        self.id = con_id
        self.pid = pid
        self.name = name
        self.app_id = None
        self.window_class = None
        self.rect = SimpleNamespace(x=rect.x, y=rect.y, width=rect.w, height=rect.h)
        self.fullscreen_mode = fullscreen_mode


class FakeConn:
    def __init__(self):
        self.commands = []

    def command(self, cmd):
        self.commands.append(cmd)
        return []


def runner_for(count=1):
    session = session_from_dict({
        "instances": [{"id": f"p{n}", "command": ["game"]} for n in range(1, count + 1)],
    })
    runner = Runner(session, Path("/tmp"))
    runner.slots = {f"p{n}": Rect((n - 1) * 100, 0, 100, 100) for n in range(1, count + 1)}
    runner.roots = {1000 + n: f"p{n}" for n in range(1, count + 1)}
    return runner


# --- what counts as correctly placed ----------------------------------------


def test_a_fullscreen_window_is_not_correctly_placed_however_its_rect_reads():
    # sway reports the geometry a fullscreen window would return to, so the
    # rect alone says the window is exactly where we put it.
    assert not matches(FakeCon(fullscreen_mode=1), SLOT)
    assert matches(FakeCon(fullscreen_mode=0), SLOT)


def test_a_container_that_cannot_be_fullscreen_is_judged_on_its_rect():
    con = FakeCon()
    con.fullscreen_mode = None  # workspaces and outputs report it this way
    assert matches(con, SLOT)


def test_placing_a_window_takes_it_out_of_fullscreen_first():
    conn = FakeConn()
    session_mod.place(conn, 7, SLOT)
    cmd = conn.commands[0]
    assert "fullscreen disable" in cmd
    assert cmd.index("fullscreen disable") < cmd.index("resize set")


def test_the_nested_compositor_refuses_fullscreen_at_map_time():
    # Belt to the repair loop's braces, and it also covers windows we never place.
    assert "fullscreen disable" in NESTED_CONFIG


# --- repairing --------------------------------------------------------------


def test_a_window_that_fullscreens_is_put_back():
    runner, conn = runner_for(), FakeConn()
    runner.repair(conn, FakeCon(fullscreen_mode=1), "p1")
    assert conn.commands and "fullscreen disable" in conn.commands[0]


def test_fullscreen_is_undone_even_after_the_size_cap_is_spent():
    runner, conn = runner_for(), FakeConn()
    runner.retries = {1: session_mod.SETTLE_ROUNDS}
    runner.repair(conn, FakeCon(fullscreen_mode=1), "p1")
    # `fullscreen disable` is the compositor's decision, not a request the
    # client can refuse, so there is no fight to give up on.
    assert len(conn.commands) == 1


def test_a_client_that_refuses_its_size_is_only_fought_so_long():
    runner, conn = runner_for(), FakeConn()
    wrong = FakeCon(rect=Rect(10, 10, 640, 480))
    for _ in range(session_mod.SETTLE_ROUNDS + 5):
        runner.repair(conn, wrong, "p1")
    assert len(conn.commands) == session_mod.SETTLE_ROUNDS


def test_a_window_that_settles_and_later_escapes_gets_a_fresh_set_of_attempts():
    runner, conn = runner_for(), FakeConn()
    wrong = FakeCon(rect=Rect(10, 10, 640, 480))
    for _ in range(session_mod.SETTLE_ROUNDS):
        runner.repair(conn, wrong, "p1")
    runner.repair(conn, FakeCon(), "p1")            # the window obeyed
    runner.repair(conn, wrong, "p1")                # ...and then changed resolution
    assert len(conn.commands) == session_mod.SETTLE_ROUNDS + 1


def test_a_correctly_placed_window_is_left_alone():
    runner, conn = runner_for(), FakeConn()
    runner.repair(conn, FakeCon(), "p1")
    assert conn.commands == []


# --- through the event loop -------------------------------------------------


def event(con, change):
    return SimpleNamespace(container=con, change=change)


def test_a_fullscreen_event_on_a_placed_window_repairs_it():
    runner, conn = runner_for(), FakeConn()
    runner.placed = {1: "p1"}
    runner.on_window(conn, event(FakeCon(fullscreen_mode=1), "fullscreen_mode"))
    assert conn.commands and "fullscreen disable" in conn.commands[0]


def test_a_window_waiting_for_a_slot_is_still_denied_fullscreen():
    # It has no slot yet (an instance with several windows, waiting for a
    # title that says which is which), but it can still cover the frame.
    runner, conn = runner_for(), FakeConn()
    runner.pending = {1: "p1"}
    runner.on_window(conn, event(FakeCon(fullscreen_mode=1), "fullscreen_mode"))
    assert conn.commands == ["[con_id=1] fullscreen disable"]
    assert runner.placed == {}


def test_a_placed_window_that_closes_is_forgotten():
    runner, conn = runner_for(), FakeConn()
    runner.placed, runner.retries = {1: "p1"}, {1: 3}
    runner.on_window(conn, event(FakeCon(), "close"))
    assert runner.placed == {} and runner.retries == {}
    assert conn.commands == []
