"""Pure: decide which slot a freshly mapped window belongs to.

Slots are identified by WindowSpec ids. For a single-window instance the one
slot is taken by the first window from that process. For multi-window
instances every slot has a regex which is tested against the window's title,
app_id and X11 class; the window waits (returns None) until a title matches,
because Qt/Xwayland windows usually get their real title after mapping.
"""
from __future__ import annotations

import re
from collections.abc import Collection, Sequence

from .config import WindowSpec


def assign_slot(
    specs: Sequence[WindowSpec],
    taken: Collection[str],
    title: str | None,
    app_id: str | None = None,
    window_class: str | None = None,
) -> str | None:
    free = [w for w in specs if w.id not in taken]
    if not free:
        return None
    haystack = [t for t in (title, app_id, window_class) if t]
    for spec in free:
        if spec.match is None:
            return spec.id
        if any(re.search(spec.match, h) for h in haystack):
            return spec.id
    return None
