"""Session config: validated, immutable description of what to launch."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import modes


@dataclass(frozen=True)
class WindowSpec:
    """One layout slot produced by an instance. `match` is a regex tested against the
    window title, app_id and X11 class; needed only when one process opens several
    windows (Dolphin main + GBA1..4). A single unmatched window is the default."""
    id: str
    match: str | None = None


@dataclass(frozen=True)
class Instance:
    id: str
    command: tuple[str, ...]
    devices: tuple[str, ...] = ()          # evdev nodes this instance may see
    keyboard_to_pad: str | None = None     # keyboard node to convert into a private virtual gamepad
    isolate_input: bool = False            # wrap in bwrap and hide all other /dev/input nodes
    gamescope: bool = False                # wrap in a nested gamescope at the slot size
    env: tuple[tuple[str, str], ...] = ()
    binds: tuple[tuple[str, str], ...] = ()  # (host, sandbox) dirs, e.g. per-player saves
    cwd: str | None = None
    windows: tuple[WindowSpec, ...] = ()     # empty = one window, id == instance id, no match rule
    pre_launch: tuple[tuple[str, ...], ...] = ()  # commands run (and awaited) before the instance; failure aborts

    @property
    def window_specs(self) -> tuple[WindowSpec, ...]:
        return self.windows or (WindowSpec(self.id),)


@dataclass(frozen=True)
class Session:
    instances: tuple[Instance, ...]
    layout: str = "grid"
    layout_args: dict = field(default_factory=dict)
    width: int | None = None   # None = use whatever size the nested compositor gets
    height: int | None = None


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


def instance_from_dict(d: dict) -> Instance:
    _require(isinstance(d.get("id"), str) and d["id"], "instance needs a non-empty string id")
    cmd = d.get("command")
    _require(isinstance(cmd, list) and cmd and all(isinstance(c, str) for c in cmd),
             f"instance {d['id']}: command must be a non-empty list of strings")
    devices = tuple(d.get("devices", ()))
    _require(all(isinstance(x, str) for x in devices), f"instance {d['id']}: devices must be strings")
    binds = tuple((str(a), str(b)) for a, b in d.get("binds", ()))
    windows = tuple(window_from_dict(d["id"], w) for w in d.get("windows", ()))
    _require(not (d.get("gamescope") and len(windows) > 1),
             f"instance {d['id']}: gamescope presents one window, but this instance declares "
             f"{len(windows)}; the other slots would stay empty")
    pre = d.get("pre_launch", [])
    _require(isinstance(pre, list) and all(isinstance(c, list) and c and all(isinstance(a, str) for a in c) for c in pre),
             f"instance {d['id']}: pre_launch must be a list of non-empty argv lists")
    return Instance(
        id=d["id"], command=tuple(cmd), devices=devices,
        keyboard_to_pad=d.get("keyboard_to_pad"),
        isolate_input=bool(d.get("isolate_input", bool(devices) or bool(d.get("keyboard_to_pad")))),
        gamescope=bool(d.get("gamescope", False)),
        env=tuple((str(k), str(v)) for k, v in d.get("env", {}).items()),
        binds=binds, cwd=d.get("cwd"), windows=windows,
        pre_launch=tuple(tuple(c) for c in pre),
    )


def window_from_dict(inst_id: str, d: dict) -> WindowSpec:
    _require(isinstance(d.get("id"), str) and d["id"], f"instance {inst_id}: every window needs an id")
    match = d.get("match")
    if match is not None:
        _require(isinstance(match, str), f"window {d['id']}: match must be a regex string")
        try:
            re.compile(match)
        except re.error as exc:
            raise ValueError(f"window {d['id']}: bad regex {match!r}: {exc}") from exc
    return WindowSpec(id=d["id"], match=match)


def with_gamescope_default(d: dict, default: bool) -> dict:
    """Apply a session-wide `gamescope` to an instance that does not decide for itself.

    Returns a new dict; an instance that names `gamescope` itself is left alone.

    Skipped for an instance that opens several windows, rather than refused:
    gamescope shows one window, so a Dolphin with four GBA views would arrive
    as a single surface and four of the five slots would stay empty. Asked for
    on that instance it is an error (`instance_from_dict`); inherited from the
    session it simply is not for that instance, so `"gamescope": true` at the
    top of a config stays a thing you can always write.
    """
    if not default or "gamescope" in d or len(d.get("windows", ())) > 1:
        return d
    return {**d, "gamescope": True}


def session_from_dict(d: dict) -> Session:
    # A mode writes the instances, windows and layout that a known game's split
    # screen always has; anything the config states itself is left alone.
    d = modes.expand(d)
    insts = d.get("instances")
    _require(isinstance(insts, list) and insts, "config needs a non-empty 'instances' list")
    # A session-wide default, because the reason to want gamescope -- a game
    # that sizes its own window, or changes resolution mid-play -- is a
    # property of the game, and every instance is the same game.
    gamescope = bool(d.get("gamescope", False))
    instances = tuple(instance_from_dict(with_gamescope_default(i, gamescope)) for i in insts)
    ids = [i.id for i in instances]
    _require(len(ids) == len(set(ids)), "instance ids must be unique")
    slot_ids = [w.id for i in instances for w in i.window_specs]
    _require(len(slot_ids) == len(set(slot_ids)), "window ids must be unique across all instances")
    layout = d.get("layout", {"name": "grid"})
    if isinstance(layout, str):
        layout = {"name": layout}
    frame = d.get("frame", {})
    return Session(
        instances=instances, layout=layout.get("name", "grid"),
        layout_args={k: v for k, v in layout.items() if k != "name"},
        width=frame.get("width"), height=frame.get("height"),
    )


def load(path: str | Path) -> Session:
    with open(path, encoding="utf-8") as fh:
        return session_from_dict(json.load(fh))
