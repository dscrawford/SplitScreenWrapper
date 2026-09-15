"""Modes: a game whose split screen is a known shape, written out in full.

A config names instances, windows, a layout and any pre_launch steps. For a
game nobody has met before that is the right amount of detail. For one we have
met — Four Swords Adventures, whose layout, window titles, emulator overrides
and controller ports all follow from "how many players?" — writing those four
things by hand means keeping them in step by hand.

So a config may name a mode instead, and the mode writes them:

    {"frame": {...}, "mode": {"name": "fsa", "players": 3, "gc": "...", "gba_bios": "..."}}

Anything the config states itself wins, so a mode is a starting point rather
than a cage: keep the generated instance and hand-tune the layout, or the
other way round.
"""
from __future__ import annotations

from . import fsa

MODES = {"fsa": fsa.expand}


def expand(config: dict) -> dict:
    """A config with its mode replaced by what the mode generates."""
    spec = config.get("mode")
    if spec is None:
        return config
    if not isinstance(spec, dict):
        raise ValueError("mode must be an object, e.g. {\"name\": \"fsa\", \"players\": 2}")
    name = spec.get("name")
    try:
        make = MODES[name]
    except KeyError as exc:
        raise ValueError(f"unknown mode {name!r}; choose from {sorted(MODES)}") from exc

    generated = make(spec)
    rest = {k: v for k, v in config.items() if k != "mode"}
    return {**generated, **rest}
