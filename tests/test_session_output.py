from types import SimpleNamespace as NS
from splitscreen.session import pick_output


def out(active=True, w=1280, h=720):
    return NS(active=active, rect=NS(width=w, height=h))


def test_first_active_output_wins():
    assert pick_output([out(active=False), out(w=800, h=600)]) == (800, 600)


def test_no_outputs_is_none():
    assert pick_output([]) is None
    assert pick_output([out(active=False), out(w=0, h=0)]) is None
