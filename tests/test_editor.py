import json
import subprocess
import sys

from splitscreen.editor import (Frac, coverage, move_slot, preset, resize_slot, save_layout, snap,
                                layout_from_config, slot_count_from_config)


def test_snap_only_within_tolerance():
    assert snap(0.248, (0.0, 0.25, 1.0), 0.01) == 0.25
    assert snap(0.20, (0.0, 0.25, 1.0), 0.01) == 0.20


def test_move_snaps_right_edge_to_neighbour():
    slots = (Frac(0, 0, 0.25, 1), Frac(0.5, 0, 0.5, 1))
    moved = move_slot(slots, 0, 0.243, 0.0, 0.01)   # right edge at 0.493 -> snaps to 0.5
    assert abs(moved[0].x + moved[0].w - 0.5) < 1e-9 and moved[1] == slots[1]


def test_resize_clamps_inside_frame_and_min_size():
    slots = (Frac(0.5, 0.5, 0.25, 0.25),)
    big = resize_slot(slots, 0, 1.3, 1.3, 0.0)
    assert big[0].x + big[0].w <= 1.0 and big[0].y + big[0].h <= 1.0
    tiny = resize_slot(slots, 0, 0.5, 0.5, 0.0)
    assert tiny[0].w >= 0.05 and tiny[0].h >= 0.05


def test_presets_cover_frame_without_overlap():
    for name, n in (("grid", 4), ("sidebar", 3), ("tri", 3)):
        cov, over = coverage(preset(name, n), 100)
        assert cov == 1.0 and not over, name


def test_hub_preset_leaves_gaps_but_no_overlap():
    cov, over = coverage(preset("hub", 5), 100)
    assert 0.5 <= cov < 1.0 and not over


def test_config_helpers_count_windows_and_read_free_layout():
    cfg = {"instances": [{"id": "a", "windows": [{"id": "w1"}, {"id": "w2"}]}, {"id": "b"}],
           "layout": {"name": "free", "slots": [{"x": 0, "y": 0, "w": 0.5, "h": 1}, {"x": 0.5, "y": 0, "w": 0.5, "h": 0.5}, {"x": 0.5, "y": 0.5, "w": 0.5, "h": 0.5}]}}
    assert slot_count_from_config(cfg) == 3
    assert layout_from_config(cfg, 3)[1] == Frac(0.5, 0, 0.5, 0.5)


def test_save_layout_keeps_other_keys(tmp_path):
    p = tmp_path / "c.json"
    out = save_layout(p, {"frame": {"width": 10, "height": 10}, "instances": []}, (Frac(0, 0, 1, 1),))
    assert out["frame"] == {"width": 10, "height": 10}
    assert json.loads(p.read_text())["layout"] == {"name": "free", "slots": [{"x": 0, "y": 0, "w": 1, "h": 1}]}


def test_cli_save_and_exit_writes_sidebar_layout(tmp_path):
    p = tmp_path / "s.json"
    r = subprocess.run([sys.executable, "-m", "splitscreen.editor", str(p), "--slots", "3", "--preset", "sidebar", "--save-and-exit"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    slots = json.loads(p.read_text())["layout"]["slots"]
    assert slots[0]["w"] == 0.25 and slots[2] == {"x": 0.25, "y": 0, "w": 0.75, "h": 1}
