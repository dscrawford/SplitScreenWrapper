import json
import pytest
from splitscreen.config import instance_from_dict, session_from_dict, load


def test_minimal_instance_defaults():
    i = instance_from_dict({"id": "p1", "command": ["game"]})
    assert i.command == ("game",) and not i.isolate_input and not i.gamescope and i.devices == ()


def test_devices_imply_isolation():
    i = instance_from_dict({"id": "p1", "command": ["game"], "devices": ["/dev/input/event3"]})
    assert i.isolate_input and i.devices == ("/dev/input/event3",)


def test_keyboard_to_pad_implies_isolation():
    i = instance_from_dict({"id": "p1", "command": ["game"], "keyboard_to_pad": "/dev/input/event9"})
    assert i.isolate_input


@pytest.mark.parametrize("bad", [
    {"command": ["x"]}, {"id": "", "command": ["x"]}, {"id": "a"}, {"id": "a", "command": []},
    {"id": "a", "command": "game"}, {"id": "a", "command": ["x"], "devices": [3]},
])
def test_rejects_bad_instance(bad):
    with pytest.raises(ValueError):
        instance_from_dict(bad)


def test_session_defaults_and_layout_args():
    s = session_from_dict({"instances": [{"id": "a", "command": ["x"]}],
                           "layout": {"name": "hub", "center_fraction": 0.6}})
    assert s.layout == "hub" and s.layout_args == {"center_fraction": 0.6} and s.width is None


def test_session_layout_as_string():
    assert session_from_dict({"instances": [{"id": "a", "command": ["x"]}], "layout": "grid"}).layout == "grid"


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError):
        session_from_dict({"instances": [{"id": "a", "command": ["x"]}, {"id": "a", "command": ["y"]}]})


def test_load_example_files(tmp_path):
    cfg = {"frame": {"width": 100, "height": 50}, "instances": [{"id": "a", "command": ["x"]}]}
    f = tmp_path / "c.json"
    f.write_text(json.dumps(cfg))
    s = load(f)
    assert (s.width, s.height) == (100, 50)


def test_windows_default_to_one_slot_named_after_instance():
    i = instance_from_dict({"id": "p1", "command": ["x"]})
    assert [w.id for w in i.window_specs] == ["p1"] and i.window_specs[0].match is None


def test_windows_with_regexes():
    i = instance_from_dict({"id": "d", "command": ["x"], "windows": [{"id": "main", "match": "^Dolphin"}, {"id": "gba1", "match": "^GBA1"}]})
    assert [w.id for w in i.window_specs] == ["main", "gba1"]


@pytest.mark.parametrize("bad", [[{"match": "^x"}], [{"id": "a", "match": 3}], [{"id": "a", "match": "("}]])
def test_bad_window_specs_rejected(bad):
    with pytest.raises(ValueError):
        instance_from_dict({"id": "d", "command": ["x"], "windows": bad})


def test_window_ids_unique_across_instances():
    with pytest.raises(ValueError):
        session_from_dict({"instances": [
            {"id": "a", "command": ["x"], "windows": [{"id": "w"}]},
            {"id": "b", "command": ["y"], "windows": [{"id": "w"}]},
        ]})


def test_pre_launch_parsed_and_validated():
    i = instance_from_dict({"id": "a", "command": ["x"], "pre_launch": [["echo", "hi"], ["true"]]})
    assert i.pre_launch == (("echo", "hi"), ("true",))
    for bad in (["echo hi"], [[]], [[1]]):
        with pytest.raises(ValueError):
            instance_from_dict({"id": "a", "command": ["x"], "pre_launch": bad})


# --- gamescope --------------------------------------------------------------


def test_gamescope_is_per_instance():
    s = session_from_dict({"instances": [
        {"id": "a", "command": ["x"], "gamescope": True},
        {"id": "b", "command": ["x"]},
    ]})
    assert [i.gamescope for i in s.instances] == [True, False]


def test_a_session_wide_gamescope_reaches_every_instance():
    # The reason to want it -- a game that sizes its own window -- belongs to
    # the game, and every instance is the same game.
    s = session_from_dict({"gamescope": True, "instances": [
        {"id": "a", "command": ["x"]}, {"id": "b", "command": ["x"]},
    ]})
    assert all(i.gamescope for i in s.instances)


def test_an_instance_overrides_the_session_wide_gamescope():
    s = session_from_dict({"gamescope": True, "instances": [
        {"id": "a", "command": ["x"], "gamescope": False}, {"id": "b", "command": ["x"]},
    ]})
    assert [i.gamescope for i in s.instances] == [False, True]


def test_gamescope_is_refused_for_an_instance_with_several_windows():
    # gamescope presents one window, so the other slots would stay empty.
    with pytest.raises(ValueError, match="one window"):
        instance_from_dict({"id": "a", "command": ["x"], "gamescope": True,
                            "windows": [{"id": "main"}, {"id": "gba1", "match": "GBA1"}]})


def test_a_session_wide_gamescope_skips_a_multi_window_instance():
    # Inherited rather than asked for: not an error, just not for that one.
    s = session_from_dict({"gamescope": True, "instances": [
        {"id": "a", "command": ["x"], "windows": [{"id": "main"}, {"id": "gba1", "match": "GBA1"}]},
        {"id": "b", "command": ["x"]},
    ]})
    assert [i.gamescope for i in s.instances] == [False, True]
