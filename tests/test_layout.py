import pytest
from splitscreen.layout import Rect, grid, hub, compute


def test_grid_single_fills_frame():
    assert grid(1, 1280, 720) == (Rect(0, 0, 1280, 720),)


def test_grid_two_is_side_by_side():
    assert grid(2, 1280, 720) == (Rect(0, 0, 640, 720), Rect(640, 0, 640, 720))


def test_grid_four_is_2x2():
    rects = grid(4, 1280, 720)
    assert rects == (
        Rect(0, 0, 640, 360), Rect(640, 0, 640, 360),
        Rect(0, 360, 640, 360), Rect(640, 360, 640, 360),
    )


def test_grid_three_leaves_cell_empty_not_stretched():
    rects = grid(3, 1280, 720)
    assert len(rects) == 3 and all(r.w == 640 and r.h == 360 for r in rects)


def test_grid_rejects_zero():
    with pytest.raises(ValueError):
        grid(0, 100, 100)


def test_hub_center_plus_corners():
    rects = hub(5, 1000, 800)
    assert rects[0] == Rect(250, 200, 500, 400)
    assert rects[1] == Rect(0, 0, 250, 200)
    assert rects[2] == Rect(750, 0, 250, 200)
    assert rects[3] == Rect(0, 600, 250, 200)
    assert rects[4] == Rect(750, 600, 250, 200)


def test_hub_slots_do_not_overlap():
    rects = hub(5, 1000, 800)
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert a.x + a.w <= b.x or b.x + b.w <= a.x or a.y + a.h <= b.y or b.y + b.h <= a.y


def test_hub_bounds():
    with pytest.raises(ValueError):
        hub(6, 100, 100)
    with pytest.raises(ValueError):
        hub(2, 100, 100, center_fraction=1.0)


def test_compute_dispatch_and_unknown():
    assert compute("grid", 2, 10, 10) == grid(2, 10, 10)
    with pytest.raises(ValueError):
        compute("nope", 1, 10, 10)


from splitscreen.layout import Frac, free, tree, tree_fracs, PRESETS


def covers_frame_without_overlap(rects, w, h):
    area = sum(r.w * r.h for r in rects)
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert a.x + a.w <= b.x or b.x + b.w <= a.x or a.y + a.h <= b.y or b.y + b.h <= a.y
    return area == w * h


def test_sidebar_preset_two_stacked_left_big_right_no_gaps():
    rects = tree(3, 1920, 1080, split=PRESETS["sidebar"])
    assert rects[0] == Rect(0, 0, 480, 540)
    assert rects[1] == Rect(0, 540, 480, 540)
    assert rects[2] == Rect(480, 0, 1440, 1080)
    assert covers_frame_without_overlap(rects, 1920, 1080)


def test_tri_preset_two_on_top_one_full_width_below():
    rects = tree(3, 1280, 720, split=PRESETS["tri"])
    assert rects[0] == Rect(0, 0, 640, 360) and rects[1] == Rect(640, 0, 640, 360)
    assert rects[2] == Rect(0, 360, 1280, 360)
    assert covers_frame_without_overlap(rects, 1280, 720)


def test_grid4_preset_matches_grid():
    assert tree(4, 1280, 720, split=PRESETS["grid4"]) == grid(4, 1280, 720)


def test_tree_rejects_wrong_leaf_count_and_bad_ratio():
    with pytest.raises(ValueError):
        tree(2, 100, 100, split=PRESETS["tri"])
    with pytest.raises(ValueError):
        tree_fracs({"split": "h", "ratio": [1], "children": [{}, {}]})
    with pytest.raises(ValueError):
        tree_fracs({"split": "x", "children": [{}, {}]})


def test_free_layout_rounds_to_pixels_and_validates():
    rects = free(2, 1000, 500, slots=[{"x": 0, "y": 0, "w": 0.333, "h": 1}, {"x": 0.333, "y": 0, "w": 0.667, "h": 1}])
    assert rects == (Rect(0, 0, 333, 500), Rect(333, 0, 667, 500))
    with pytest.raises(ValueError):
        free(1, 10, 10, slots=[{"x": 0, "y": 0, "w": 1.5, "h": 1}])
    with pytest.raises(ValueError):
        free(2, 10, 10, slots=[{"x": 0, "y": 0, "w": 1, "h": 1}])


def test_frac_roundtrip_edges_meet_exactly():
    a, b = Frac(0, 0, 0.3333, 1).to_rect(1920, 1080), Frac(0.3333, 0, 0.6667, 1).to_rect(1920, 1080)
    assert a.x + a.w == b.x
