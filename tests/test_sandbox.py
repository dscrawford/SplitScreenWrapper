from splitscreen.sandbox import bwrap_argv


import pytest


@pytest.fixture(autouse=True)
def no_hidraw(monkeypatch):
    monkeypatch.setattr("splitscreen.sandbox.hidraw_siblings", lambda p: ())
    monkeypatch.setattr("splitscreen.sandbox.all_hidraw_nodes", lambda: ())


def test_hidraw_masked_except_allowed_device(monkeypatch):
    monkeypatch.setattr("splitscreen.sandbox.sibling_nodes", lambda p: ())
    monkeypatch.setattr("splitscreen.sandbox.hidraw_siblings", lambda p: ("/dev/hidraw2",))
    monkeypatch.setattr("splitscreen.sandbox.all_hidraw_nodes", lambda: ("/dev/hidraw1", "/dev/hidraw2"))
    argv = bwrap_argv(["game"], ["/dev/input/event5"])
    assert ("--bind", "/dev/null", "/dev/hidraw1") == argv[10:13]
    assert "/dev/hidraw2" not in argv


def test_masks_dev_input_and_exposes_only_allowed(monkeypatch):
    monkeypatch.setattr("splitscreen.sandbox.sibling_nodes", lambda p: ("/dev/input/js0",) if p.endswith("event5") else ())
    argv = bwrap_argv(["game", "--flag"], ["/dev/input/event5"])
    assert argv[:6] == ("bwrap", "--die-with-parent", "--dev-bind", "/", "/", "--tmpfs")
    assert argv[6] == "/dev/input"
    assert ("--dev-bind", "/dev/input/event5", "/dev/input/event5") == argv[7:10]
    assert ("--dev-bind", "/dev/input/js0", "/dev/input/js0") == argv[10:13]
    assert argv[-3:] == ("--", "game", "--flag")


def test_no_devices_means_no_input_at_all(monkeypatch):
    monkeypatch.setattr("splitscreen.sandbox.sibling_nodes", lambda p: ())
    argv = bwrap_argv(["game"], [])
    assert "--tmpfs" in argv and argv.count("--dev-bind") == 1


def test_extra_binds_for_save_dirs(monkeypatch):
    monkeypatch.setattr("splitscreen.sandbox.sibling_nodes", lambda p: ())
    argv = bwrap_argv(["game"], [], extra_binds=[("/tmp/p2", "/home/u/.config/game")])
    i = argv.index("--bind")
    assert argv[i + 1:i + 3] == ("/tmp/p2", "/home/u/.config/game")
