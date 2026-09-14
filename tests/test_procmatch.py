from splitscreen.procmatch import find_instance, parent_pid


def test_direct_root_match():
    assert find_instance(100, {100: "p1"}, parent_of=lambda p: None) == "p1"


def test_walks_ancestors_through_wrappers():
    tree = {300: 200, 200: 100, 100: 1}  # game(300) <- bwrap(200) <- gamescope(100)
    assert find_instance(300, {100: "p2"}, parent_of=tree.get) == "p2"


def test_unknown_lineage_returns_none():
    tree = {300: 200, 200: 1}
    assert find_instance(300, {999: "p1"}, parent_of=tree.get) is None


def test_stops_on_cycle_or_depth():
    assert find_instance(5, {9: "x"}, parent_of=lambda p: p, max_depth=3) is None


def test_parent_pid_of_self_is_real():
    import os
    assert parent_pid(os.getpid()) == os.getppid()
