from splitscreen.assign import assign_slot
from splitscreen.config import WindowSpec

FSA = (
    WindowSpec("main", r"^Dolphin"),
    WindowSpec("gba1", r"^GBA1\b"),
    WindowSpec("gba2", r"^GBA2\b"),
    WindowSpec("gba3", r"^GBA3\b"),
    WindowSpec("gba4", r"^GBA4\b"),
)


def test_single_window_instance_takes_first_window_regardless_of_title():
    assert assign_slot((WindowSpec("p1"),), (), title=None) == "p1"


def test_single_window_instance_second_window_is_rejected():
    assert assign_slot((WindowSpec("p1"),), ("p1",), title="popup") is None


def test_dolphin_titles_route_to_the_right_slots():
    assert assign_slot(FSA, (), "Dolphin 2506 | JIT64 DC | Vulkan | HLE | Four Swords") == "main"
    assert assign_slot(FSA, ("main",), "GBA1 | Volume 100%") == "gba1"
    assert assign_slot(FSA, ("main", "gba1"), "GBA4 | Muted") == "gba4"


def test_untitled_window_waits_when_all_slots_need_a_match():
    assert assign_slot(FSA, (), title=None, app_id=None, window_class="dolphin-emu") is None
    assert assign_slot(FSA, (), title="") is None


def test_match_also_tests_app_id_and_class():
    specs = (WindowSpec("a", r"^game-a$"), WindowSpec("b", r"^game-b$"))
    assert assign_slot(specs, (), title="Untitled", app_id="game-b") == "b"
    assert assign_slot(specs, (), title="Untitled", window_class="game-a") == "a"


def test_taken_slot_is_not_reassigned_even_if_title_matches():
    assert assign_slot(FSA, ("gba1",), "GBA1 | Volume 100%") is None
