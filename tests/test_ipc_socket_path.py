"""Where the nested sway listens, and why it is not the workdir.

A unix socket path is copied into `sockaddr_un.sun_path`, 108 bytes including
its terminator. Nothing warns when it does not fit — sway strncpy's into it, so
the kernel binds the *truncated* name. The compositor comes up perfectly and the
session waits five seconds for a socket that cannot appear.

That is not hypothetical. GOTG names a workdir after the game's environment, and
`env-gamecube-usa_legend_of_zelda_four_swords_adventures-4p` makes the directory
105 characters; `<workdir>/sway.sock` is 115 bytes, and what appeared on disk
was a socket called `s`.
"""
import os
import socket
from pathlib import Path

import pytest

from splitscreen.session import SUN_PATH_MAX, ipc_socket_path

# The one that broke, verbatim.
FOUR_SWORDS = Path(
    "/home/daniel/.local/state/gotg/env/"
    "env-gamecube-usa_legend_of_zelda_four_swords_adventures-4p/splitscreen"
)


def test_the_limit_is_what_the_kernel_says():
    # Not a guess: 108 bytes of sun_path, one of them the terminator.
    d = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
    name = d / ("x" * (SUN_PATH_MAX - len(str(d)) - 1))
    assert len(str(name)) == SUN_PATH_MAX
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind(str(name))
    finally:
        sock.close()
        name.unlink(missing_ok=True)

    too_long = Path(str(name) + "y")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    with pytest.raises(OSError):
        sock.bind(str(too_long))
    sock.close()


def test_a_workdir_too_long_for_a_socket_is_not_used_for_one():
    # The bug: `<workdir>/sway.sock` is 115 bytes here.
    assert len(str(FOUR_SWORDS / "sway.sock")) > SUN_PATH_MAX
    assert len(str(ipc_socket_path(FOUR_SWORDS))) <= SUN_PATH_MAX


def test_the_socket_it_picks_can_actually_be_bound():
    # The whole failure was a path that looked fine and could not be listened
    # on, so the test is to listen on it.
    path = ipc_socket_path(FOUR_SWORDS)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind(str(path))
        sock.listen(1)
    finally:
        sock.close()
        path.unlink(missing_ok=True)


def test_two_sessions_do_not_share_a_socket():
    # Keyed by pid: a leftover from another session is not this one's, and was
    # its own bug once already.
    assert str(os.getpid()) in ipc_socket_path(FOUR_SWORDS).name


def test_a_short_workdir_gets_the_same_treatment():
    # One rule, not a special case that only fires when somebody notices. The
    # runtime directory is where a socket belongs whatever the workdir is.
    short = ipc_socket_path(Path("/tmp/x"))
    assert short == ipc_socket_path(FOUR_SWORDS)
