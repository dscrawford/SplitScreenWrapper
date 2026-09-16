"""A socket file is not a listening socket.

A workdir can be reused, and a session that was killed rather than closed
leaves its sway.sock behind. Waiting for the path alone is satisfied by that
corpse at once, and the connect that follows fails with ECONNREFUSED -- which
is what four players got, every launch after the first one they killed.
"""
import socket
import threading
import time

from splitscreen.session import wait_for, wait_for_socket


def test_a_leftover_socket_file_does_not_count(tmp_path):
    stale = tmp_path / "sway.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(stale))
    server.listen(1)
    server.close()  # the file stays; nothing is listening on it any more

    assert stale.exists()
    assert wait_for(str(stale), 0.2)            # the old test: satisfied
    assert not wait_for_socket(str(stale), 0.3)  # the new one: not fooled


def test_a_socket_being_listened_on_counts(tmp_path):
    live = tmp_path / "sway.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(live))
    server.listen(1)
    try:
        assert wait_for_socket(str(live), 1.0)
    finally:
        server.close()


def test_it_waits_for_one_that_arrives_late(tmp_path):
    late = tmp_path / "sway.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

    def listen_soon():
        time.sleep(0.3)
        server.bind(str(late))
        server.listen(1)

    thread = threading.Thread(target=listen_soon)
    thread.start()
    try:
        assert wait_for_socket(str(late), 3.0)
    finally:
        thread.join()
        server.close()


def test_nothing_there_at_all_times_out(tmp_path):
    assert not wait_for_socket(str(tmp_path / "never"), 0.2)
