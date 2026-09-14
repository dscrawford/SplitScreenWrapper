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
