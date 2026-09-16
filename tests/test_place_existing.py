"""Windows that mapped before the event loop started still get placed.

The subscription used to be made *after* the games were launched, so any
window that appeared during the launch loop produced no event anybody was
listening for. With one instance that loop returns in milliseconds and nothing
can appear inside it; with several, every instance after the first waits for
the one before it, so the first game's window mapping early is not a corner
case — it is what happens every time. Player one sat unplaced in the middle of
the frame while everyone else took their corner.
"""
from pathlib import Path

from splitscreen.config import session_from_dict
from splitscreen.layout import Rect
from splitscreen.session import Runner


class FakeCon:
    def __init__(self, con_id, pid, name=None, app_id=None):
        self.id = con_id
        self.pid = pid
        self.name = name
        self.app_id = app_id
        self.window_class = None
        self.rect = Rect(0, 0, 0, 0)


class FakeTree:
    def __init__(self, cons):
        self._cons = cons

    def descendants(self):
        return self._cons


class FakeConn:
    """Records the placement commands rather than talking to a compositor."""

    def __init__(self, cons):
        self.tree = FakeTree(cons)
        self.commands = []

    def get_tree(self):
        return self.tree

    def command(self, cmd):
        self.commands.append(cmd)
        return []


def runner_for(count, cons):
    session = session_from_dict({
        "instances": [
            {"id": f"p{n}", "command": ["game", "--player", str(n)]}
            for n in range(1, count + 1)
        ],
    })
    runner = Runner(session, Path("/tmp"))
    runner.slots = {
        f"p{n}": Rect((n - 1) * 100, 0, 100, 100) for n in range(1, count + 1)
    }
    runner.roots = {con.pid: f"p{i + 1}" for i, con in enumerate(cons)}
    runner.conn = FakeConn(cons)
    return runner


def test_a_window_that_mapped_before_the_loop_is_still_placed():
    cons = [FakeCon(1, 1001)]
    runner = runner_for(1, cons)
    runner.place_existing()
    assert runner.placed == {1: "p1"}
    assert "move position 0 px 0 px" in runner.conn.commands[0]


def test_every_player_ends_up_in_their_own_slot():
    cons = [FakeCon(i + 1, 1000 + i) for i in range(4)]
    runner = runner_for(4, cons)
    runner.place_existing()
    assert runner.placed == {1: "p1", 2: "p2", 3: "p3", 4: "p4"}


def test_a_window_already_placed_is_not_placed_twice():
    cons = [FakeCon(1, 1001)]
    runner = runner_for(1, cons)
    runner.placed = {1: "p1"}
    runner.place_existing()
    # Claiming it twice would leave a later window with no free slot.
    assert runner.placed == {1: "p1"}


def test_a_window_from_something_else_is_left_alone():
    cons = [FakeCon(1, 4242)]  # a pid belonging to no instance
    runner = runner_for(1, cons)
    runner.roots = {}
    runner.place_existing()
    assert runner.placed == {}
    assert runner.conn.commands == []
