"""Four Swords Adventures: one GameCube game, one GBA screen per player.

FSA is the reason this project exists and the awkward shape it has to fit. One
Dolphin process opens the game plus one window per integrated GBA, each player
holds a controller that drives *their* GBA, and the interesting screen moves
between the television and the little one depending on where you are standing.

So the mode takes two sources and a number of players and writes the rest:

    gc        the game — a gotg entry id, or a disc image for a plain Dolphin
    gba_bios  the GBA BIOS Dolphin needs before it will boot an integrated GBA
    players   1 to 4

and produces the layout, the window rules, the Dolphin overrides that turn
ports into GBAs, and the pre_launch step that binds a controller to each of
them. The point of generating all four together is that they have to agree:
the third GBA window, the third SIDevice override and the third controller are
the same player, and nothing checks that for you if they are written by hand in
three places.

    1 player    no GBA at all; the game has the frame to itself
    2 players   both GBAs stacked down the left, game takes the rest
    3 players   two GBAs left, one top-right, game between them, one blank corner
    4 players   two GBAs left, two right, game between them

Pure: everything here builds a dict. Nothing launches, reads the disk or looks
at a controller — which is what makes the slot order and the controller order
something a test can hold to account.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Dolphin's SerialInterface device numbers, from Core/HW/SI/SI_Device.h.
GC_CONTROLLER = 6
GBA_INTEGRATED = 13

MAX_PLAYERS = 4

# How much of the frame one column of GBAs takes. A GBA screen is 240x160: a
# quarter of a 1920 frame is 480 wide, a clean 2x; a quarter of a Deck's 1280
# is 320, and Dolphin scales to whatever it gets.
SIDE_FRACTION = 0.25

# Dolphin names its integrated GBA windows GBA1..GBA4 and its own window after
# the game; both arrive on XWayland from one process, which is why the session
# needs title rules rather than PID lineage alone.
GBA_TITLE = r"^GBA{port}\b"
MAIN_TITLE = r"^Dolphin|^Four Swords"

# Where gotg keeps the Dolphin config for its GameCube environment, and the
# wrapper it reaches its own binaries through.
GOTG_WRAPPER = "~/.local/state/gotg/app/bin/gotg"
GOTG_CONFIG_DIR = "~/.local/state/gotg/env/env-gamecube/config"

DISC_SUFFIXES = (".iso", ".rvz", ".gcm", ".ciso", ".gcz", ".dol", ".elf")


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise ValueError(f"fsa mode: {message}")


def slots(players: int, side_fraction: float = SIDE_FRACTION) -> tuple[dict, ...]:
    """Where each window goes, as fractions of the frame, in slot order.

    Slot order is GBA1..GBAn and then the game, which is also the order the
    window rules and the controllers are generated in — one order, written
    once, so a player's screen and their controller cannot drift apart.

    Three players deliberately leave the fourth corner empty rather than
    growing the other three: player 3's GBA stays where it would be with four
    players, so a fourth joining changes nothing that was already on screen.
    """
    _require(1 <= players <= MAX_PLAYERS, f"players must be 1 to {MAX_PLAYERS}, got {players}")
    _require(0.0 < side_fraction < 0.5, f"side_fraction must be between 0 and 0.5, got {side_fraction}")

    if players == 1:
        return ({"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0},)

    side = side_fraction
    left = ({"x": 0.0, "y": 0.0, "w": side, "h": 0.5}, {"x": 0.0, "y": 0.5, "w": side, "h": 0.5})
    right = ({"x": 1 - side, "y": 0.0, "w": side, "h": 0.5}, {"x": 1 - side, "y": 0.5, "w": side, "h": 0.5})

    if players == 2:
        return (*left, {"x": side, "y": 0.0, "w": 1 - side, "h": 1.0})
    gbas = (*left, *right[: players - 2])
    return (*gbas, {"x": side, "y": 0.0, "w": 1 - 2 * side, "h": 1.0})


def devices(players: int, pads: list | tuple | None = None) -> tuple[str, ...]:
    """Which controller drives each GBA, in player order.

    In order and nothing clever: the first pad SDL reports drives GBA1, the
    second GBA2, and so on. `pads` overrides that per player — for a keyboard
    in the fourth seat, or for two pads that enumerate the wrong way round.
    """
    if players < 2:
        return ()
    if pads is None:
        return tuple(f"pad:{i}" for i in range(players))
    _require(
        len(pads) == players and all(isinstance(p, str) and p for p in pads),
        f"pads must name one device per player ({players} for {players} players)",
    )
    return tuple(pads)


def overrides(players: int, gba_bios: str) -> tuple[str, ...]:
    """The Dolphin config overrides: one port per player.

    Ports are filled from the first, so player one is always port 1 whether
    they are alone with a controller or the first of four with a GBA.
    """
    ports = [f"Dolphin.Core.SIDevice{i}={GBA_INTEGRATED if players > 1 else GC_CONTROLLER}" for i in range(players)]
    return (*ports, f"Dolphin.GBA.BIOS={gba_bios}", "Dolphin.Display.Fullscreen=False")


def windows(players: int) -> tuple[dict, ...]:
    """Window rules in slot order. One player is one window, which needs no
    rule at all — the session gives a lone window the only slot."""
    if players == 1:
        return ()
    gbas = [{"id": f"gba{port}", "match": GBA_TITLE.format(port=port)} for port in range(1, players + 1)]
    return (*gbas, {"id": "main", "match": MAIN_TITLE})


def _command(spec: dict, players: int) -> tuple[list[str], dict[str, str]]:
    gc = spec.get("gc")
    _require(isinstance(gc, str) and gc, "needs a 'gc' source: a gotg entry id or a disc image path")
    gba_bios = spec.get("gba_bios")
    _require(isinstance(gba_bios, str) and gba_bios, "needs a 'gba_bios': the BIOS Dolphin boots a GBA with")

    flags: list[str] = []
    for override in overrides(players, str(Path(gba_bios).expanduser())):
        flags += ["-C", override]

    # A path is a disc for a plain Dolphin; anything else is an entry id for
    # gotg, which knows where the disc lives and which emulator to build.
    if gc.endswith(DISC_SUFFIXES) or "/" in gc:
        dolphin = spec.get("dolphin", "dolphin-emu")
        return [dolphin, "-b", "-e", str(Path(gc).expanduser()), *flags], {}
    gotg = str(Path(spec.get("gotg", GOTG_WRAPPER)).expanduser())
    # GOTG_FULLSCREEN=0: a fullscreen Dolphin inside the frame would cover the
    # GBAs with the game it is meant to sit between.
    return [gotg, "play", gc, *flags], {"GOTG_FULLSCREEN": "0"}


def _pre_launch(spec: dict, players: int) -> list[list[str]]:
    """Bind the controllers before Dolphin reads GBA.ini, which it only does at
    startup. One command for every player, so the ports are written together or
    not at all."""
    if players < 2:
        return []
    config_dir = spec.get("config_dir")
    if config_dir is None:
        gc = spec.get("gc", "")
        config_dir = GOTG_CONFIG_DIR if not (gc.endswith(DISC_SUFFIXES) or "/" in gc) else "~/.config"
    argv = ["python3", "-m", "splitscreen.handlers.dolphin_gba",
            "--config-dir", str(Path(config_dir).expanduser())]
    for port, device in enumerate(devices(players, spec.get("pads")), start=1):
        argv += ["--gba", f"{port}={device}"]
    return [argv]


def expand(spec: dict) -> dict:
    """The mode's whole contribution to a session: a layout and one instance."""
    players = spec.get("players", 1)
    _require(isinstance(players, int) and not isinstance(players, bool), "players must be a whole number")
    _require(1 <= players <= MAX_PLAYERS, f"players must be 1 to {MAX_PLAYERS}, got {players}")

    command, env = _command(spec, players)
    instance: dict = {"id": spec.get("id", "fsa"), "command": command}
    if env:
        instance["env"] = env
    pre = _pre_launch(spec, players)
    if pre:
        instance["pre_launch"] = pre
    rules = windows(players)
    if rules:
        instance["windows"] = [dict(w) for w in rules]

    return {
        "layout": {"name": "free", "slots": [dict(s) for s in slots(players, spec.get("side_fraction", SIDE_FRACTION))]},
        "instances": [instance],
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--players", type=int, default=2)
    ap.add_argument("--gc", required=True, help="a gotg entry id, or the path to a disc image")
    ap.add_argument("--gba-bios", required=True, help="the GBA BIOS Dolphin boots an integrated GBA with")
    ap.add_argument("--config-dir", help="where Dolphin keeps dolphin-emu/GBA.ini")
    ap.add_argument("--dolphin", help="the Dolphin to run a disc with (default: dolphin-emu from PATH)")
    ap.add_argument("--pad", action="append", dest="pads", metavar="DEVICE",
                    help="one per player, in order: pad:N, sdl:<name> or keyboard")
    # No default: without both, the frame follows the screen it is shown on
    # (see screen.py), which is what a Deck's 1280x800 panel needs.
    ap.add_argument("--width", type=int, default=None)
    ap.add_argument("--height", type=int, default=None)
    ap.add_argument("-o", "--out", help="write the config here instead of stdout")
    args = ap.parse_args(argv)

    spec = {"name": "fsa", "players": args.players, "gc": args.gc, "gba_bios": args.gba_bios}
    if args.config_dir:
        spec["config_dir"] = args.config_dir
    if args.dolphin:
        spec["dolphin"] = args.dolphin
    if args.pads:
        spec["pads"] = args.pads
    try:
        config = expand(spec)
        if args.width and args.height:
            config = {"frame": {"width": args.width, "height": args.height}, **config}
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    text = json.dumps(config, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(text)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
