# Game-invariant split-screen on Linux: Research Report
*Generated: 2026-09-14 | Sources: 41 | Confidence: High (tooling landscape), Medium (Dolphin internals read from source, not tested)*

## Executive Summary

Nothing existing does exactly the ask (one window, any game, any layout, per-player input) on a
non-KDE Linux desktop, but the building blocks are mature and three Linux projects converge on the
same recipe: one nested `gamescope` per instance, `bubblewrap` to hide all but one player's
`/dev/input` nodes, and the desktop's window manager to tile the gamescope windows. PartyDeck is the
most complete (MIT, active again since April 2026) but requires KDE Plasma 6 for automatic tiling
and per-game handler packages. Splinux is fully game-agnostic but alpha and does no tiling. Windows
tools (Nucleus Co-op, Universal Split Screen) rely on DLL injection and do not run on Linux.
Per-player **gamepad** isolation is solved; per-player **keyboard/mouse** into native keyboard input
is the open problem everywhere (gamescope PR #1897 is unmerged). For Four Swords Adventures, Dolphin's
Integrated GBA already spawns four separate windows, so the problem reduces to layout only.

## 1. Existing tools

| Tool | Platform | Combines windows by | Input isolation | Activity | License | Game-agnostic |
|---|---|---|---|---|---|---|
| [PartyDeck](https://github.com/partydeck/partydeck) | Linux/SteamOS, KDE 6+ for auto-tiling | one gamescope per instance + KWin script (`res/splitscreen_kwin.js`) | bwrap masks evdev + hidraw; gamescope fork for kb/m | v0.8.7 on 2026-09-14 | MIT | handler-driven, GUI wizard for any game |
| [Splinux](https://github.com/Syntrait/splinux) | Linux (Xwayland in gamescope) | manual gamescope launches, no tiling | EVIOCGRAB + XTest replay per DISPLAY; uinput pads + bwrap | alpha rewrite, 2026-04 | GPL-3 | yes |
| [CouchPlay](https://github.com/hikaps/couchplay) | Linux, KDE Plasma | multiple gamescope instances, fixed layouts | temp Linux user per player, device assignment, hidraw for Steam Controller | v0.4.0, 2026-08 | GPL-3 | yes (Steam/Heroic) |
| [DualScope](https://gist.github.com/NaviVani-dev/9a8a704a31313fd5ed5fa68babf7bc3a) | Arch/KDE | two half-screen gamescopes | chown of event nodes to second user (reported insufficient) | 2026-07 | none | yes |
| [Co-op-on-Linux](https://github.com/AhmedKJ/Co-op-on-Linux) | Linux | nested weston per instance | firejail | 2026-09 | n/a | yes, 2 players |
| [Nucleus Co-op](https://github.com/SplitScreen-Me/splitscreenme-nucleus) | Windows only | resizes/repositions instance windows | per-instance xinput DLLs, ProtoInput hooks | v2.4.2, 2026-08 | GPL-3 | no, JS handler per game |
| [Universal Split Screen](https://github.com/UniversalSplitScreen/UniversalSplitScreen) | Windows only | none (user arranges) | DLL-injected hooks | 2022, superseded by ProtoInput | MIT | yes |
| [Xephyr method](https://pupuweb.com/how-play-split-screen-games-linux-xephyr/) | X11 | nested X servers | `-keybd evdev` (removed years ago) | 2023 guide | n/a | no GL accel |

Key facts:
- PartyDeck's README describes the stack verbatim: KWin session script tiles gamescope windows;
  gamescope "has the neat side effect of receiving controller input even when the window is not
  currently active"; bubblewrap "mask[s] out evdev input files from the instances"
  ([README](https://github.com/partydeck/partydeck)). Source confirms `--tmpfs /dev/input`, `--dev-bind`
  per allowed node and `--bind /dev/null` over other hidraw nodes (`src/launch.rs`).
- PartyDeck was declared final on 2026-03-04 and revived under new maintainers on 2026-04-08
  ([releases](https://github.com/partydeck/partydeck/releases)); non-KDE tiling is an open request
  (issues #119, #149, #163). GamingOnLinux coverage:
  [May 2025](https://www.gamingonlinux.com/2025/05/partydeck-is-a-split-screen-game-launcher-for-linux-steamos/),
  [July 2025 kb/m support](https://www.gamingonlinux.com/2025/07/split-screen-game-launcher-for-linux-steamos-adds-support-for-multiple-keyboards-and-mice/).
- Splinux's author moved from Xephyr to gamescope because "Xephyr doesn't have 3D acceleration"
  ([README](https://github.com/Syntrait/splinux)).
- Nucleus Co-op: "There is no official Mac or Linux version" ([FAQ](https://nucleuscoop.org/faq/)),
  Linux issue [#145](https://github.com/distrohelena/nucleuscoop/issues/145) open since 2020.
- "Tab-Nine" and "Splinter" as split-screen tools: not found; Splinter is almost certainly Splinux.

## 2. Technical building blocks

**Compositing several windows into one window**
- Wayland forbids cross-client embedding: xdg-foreign only sets a parent relation, subsurfaces are
  same-connection ([xdg-foreign-v2](https://wayland.app/protocols/xdg-foreign-unstable-v2),
  [wayland-book subsurfaces](https://wayland-book.com/surfaces-in-depth/subsurfaces.html)). The
  practical route is a nested compositor: weston `--backend wayland`
  ([weston(1)](https://man.archlinux.org/man/weston.1)), wlroots `WLR_BACKENDS=wayland`
  ([env_vars.md](https://raw.githubusercontent.com/swaywm/wlroots/master/docs/env_vars.md)), cage for a
  single app ([cage](https://github.com/cage-kiosk/cage)), or a custom Smithay compositor
  ([smithay backends](https://smithay.github.io/smithay/smithay/backend/index.html)).
- gamescope shows one focused client at a time and cannot tile two apps
  ([issue #437](https://github.com/ValveSoftware/gamescope/issues/437)); `-W/-H` output size,
  `-w/-h` game size, `--force-windows-fullscreen`, `--backend sdl|wayland|headless`
  ([main.cpp](https://raw.githubusercontent.com/ValveSoftware/gamescope/master/src/main.cpp)).
- X11: `XReparentWindow` works on foreign windows
  ([Xlib](https://tronche.com/gui/x/xlib/window-and-session-manager/XReparentWindow.html)),
  `xdotool windowreparent` scripts it, but XWayland-only under a Wayland desktop.
- WM rules as fallback: sway `for_window ... floating enable, resize set, move position`
  ([sway(5)](https://man.archlinux.org/man/sway.5)); Hyprland `windowrule`; KWin scripts (PartyDeck).

**Per-player input**
- gamescope has no shipped option to restrict which physical devices a nested instance sees
  ([issue #1771](https://github.com/ValveSoftware/gamescope/issues/1771));
  [PR #1897](https://github.com/ValveSoftware/gamescope/pull/1897) adds `--libinput-hold-dev`, unmerged
  as of Aug 2026. Gamepads bypass the compositor (games read evdev directly), hence bwrap masking.
- bwrap `--dev-bind`, `--tmpfs` ([bwrap(1)](https://www.mankier.com/1/bwrap)); SDL enumerates via udev
  and may need `SDL_JOYSTICK_DISABLE_UDEV=1` in some sandboxes
  ([bubblewrap #591](https://github.com/containers/bubblewrap/issues/591)).
- Permission-only isolation (DualScope's chown) was reported insufficient: "the controller controls
  both instances" ([gist](https://gist.github.com/NaviVani-dev/9a8a704a31313fd5ed5fa68babf7bc3a)).
- SDL hints: `SDL_GAMECONTROLLER_IGNORE_DEVICES[_EXCEPT]` (VID/PID based, cannot separate identical
  pads), `SDL_JOYSTICK_DEVICE`, `SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS`
  ([SDL env vars](https://wiki.libsdl.org/SDL3/EnvironmentVariables)).
- EVIOCGRAB + uinput virtual devices: evsieve implements grab and re-emit with stable links
  ([evsieve](https://github.com/KarsMulder/evsieve)); kernel uinput doc
  ([docs.kernel.org](https://docs.kernel.org/input/uinput.html)).
- X11 MPX (`xinput create-master`, `XIGrabDevice`) only helps XI2-aware apps; SDL games use the
  core pointer ([X.Org MPX](https://www.x.org/Development/Documentation/MPX/)).
- systemd multiseat needs one GPU per seat, so it is not a split-screen route
  ([Gentoo Multiseat](https://wiki.gentoo.org/wiki/Multiseat)).

## 3. Four Swords Adventures on Linux

- Dolphin's Integrated GBA (libmgba) boots a GBA per configured port; netplay runs every GBA on
  every client ([Dolphin blog 2021-07](https://dolphin-emu.org/blog/2021/07/21/integrated-gba/)).
  Borderless and always-on-top options exist "to make fitting things onto a single monitor easier"
  ([progress report](https://dolphin-emu.org/blog/2021/08/01/dolphin-progress-report-june-and-july-2021/)).
- Each GBA is a top-level `QWidget(nullptr, ...)` with per-pad persisted geometry
  (`gbawidget/geometry%1`); there is no option to render GBAs inside the main window
  ([GBAWidget.cpp](https://raw.githubusercontent.com/dolphin-emu/dolphin/master/Source/Core/DolphinQt/GBAWidget.cpp)).
- Dolphin forces `QT_QPA_PLATFORM=xcb` on Wayland since 2506
  ([PR #13286](https://github.com/dolphin-emu/dolphin/pull/13286)), so all windows are XWayland
  windows with class `dolphin-emu`; GBA titles are `GBA1`..`GBA4` (`| Volume 100%` suffix), render
  window role `renderer`. FSA wiki: "no reported problems"
  ([wiki](https://wiki.dolphin-emu.org/index.php?title=The_Legend_of_Zelda:_Four_Swords_Adventures)).
- Only prior layout implementation found: Batocera's ratpoison frames (main 3/4 width, GBAs in a
  column) ([PR #7531](https://github.com/batocera-linux/batocera.linux/pull/7531)); whether it still
  ships after Batocera's move to sway/labwc is unverified.
- Same setup applies to Final Fantasy Crystal Chronicles and Pac-Man Vs.
  ([FFCC wiki](https://wiki.dolphin-emu.org/index.php?title=Final_Fantasy_Crystal_Chronicles)).
- Emulators generally: Dolphin `-u DIR` / `DOLPHIN_EMU_USERPATH` for per-instance configs
  ([wiki](https://github.com/dolphin-emu/dolphin/wiki/User-and-Data-Folders)); RetroArch
  `--appendconfig` and index-based `input_playerN_joypad_index`; mGBA multiplayer is single-process
  and one pad drives all windows ([mgba #276](https://github.com/mgba-emu/mgba/issues/276)).

## Key Takeaways

- Build on the proven recipe (nested compositor per frame, bwrap for devices) rather than X11
  reparenting, which is dead on Wayland desktops.
- Own the frame: a nested compositor you control gives "one window" for free and removes the
  KDE-only dependency that limits PartyDeck. This is what the MVP in this repo does with nested sway.
- Match windows by PID lineage, not by title/class, to stay game-invariant; add title matching only
  for single-process multi-window cases such as Dolphin's GBAs.
- Keyboards are best turned into virtual gamepads (uinput) until a compositor with per-instance
  device holding is available.
- Gaps: Reddit was not crawlable; Hyprland wiki and some man pages 403'd (syntax taken from
  snippets); Batocera's current GBA layout status is unverified.

## Sources

1. https://github.com/partydeck/partydeck — split-screen launcher, gamescope + bwrap + KWin script
2. https://github.com/partydeck/partydeck/releases — release history, "final" then revival
3. https://www.gamingonlinux.com/2025/05/partydeck-is-a-split-screen-game-launcher-for-linux-steamos/
4. https://www.gamingonlinux.com/2025/07/split-screen-game-launcher-for-linux-steamos-adds-support-for-multiple-keyboards-and-mice/
5. https://github.com/davidawesome02-backup/gamescope — PartyDeck's keyboard/mouse gamescope fork
6. https://github.com/Syntrait/splinux — evdev grab + XTest replay, uinput pads
7. https://github.com/hikaps/couchplay — gamescope instances with per-player Linux users
8. https://gist.github.com/NaviVani-dev/9a8a704a31313fd5ed5fa68babf7bc3a — DualScope
9. https://github.com/AhmedKJ/Co-op-on-Linux — weston + firejail, 2 players
10. https://github.com/blckink/split-happens — PartyDeck fork
11. https://github.com/ArnoldSmith86/minecraft-splitscreen — game-specific Steam Deck split-screen
12. https://github.com/SplitScreen-Me/splitscreenme-nucleus — Nucleus Co-op
13. https://nucleuscoop.org/faq/ — no Linux version
14. https://github.com/distrohelena/nucleuscoop/issues/145 — Linux request
15. https://github.com/UniversalSplitScreen/UniversalSplitScreen — hook-based Windows tool
16. https://universalsplitscreen.github.io/docs/importantnotes/ — hooking mechanism
17. https://github.com/SplitScreen-Me/splitscreenme-protoInput — ProtoInput fork
18. https://pupuweb.com/how-play-split-screen-games-linux-xephyr/ — Xephyr approach
19. https://github.com/ValveSoftware/gamescope — gamescope
20. https://raw.githubusercontent.com/ValveSoftware/gamescope/master/src/main.cpp — CLI options
21. https://github.com/ValveSoftware/gamescope/issues/437 — one focused window per gamescope
22. https://github.com/ValveSoftware/gamescope/issues/1771 — per-device input request
23. https://github.com/ValveSoftware/gamescope/pull/1897 — libinput device holding PR
24. https://wayland.app/protocols/xdg-foreign-unstable-v2 — no cross-client embedding
25. https://wayland-book.com/surfaces-in-depth/subsurfaces.html — subsurfaces
26. https://man.archlinux.org/man/weston.1 — nested weston
27. https://raw.githubusercontent.com/swaywm/wlroots/master/docs/env_vars.md — WLR_BACKENDS
28. https://github.com/cage-kiosk/cage — kiosk compositor
29. https://smithay.github.io/smithay/smithay/backend/index.html — Smithay backends
30. https://man.archlinux.org/man/sway.5 — for_window rules and criteria
31. https://tronche.com/gui/x/xlib/window-and-session-manager/XReparentWindow.html — X11 reparenting
32. https://www.x.org/Development/Documentation/MPX/ — multi-pointer X
33. https://www.mankier.com/1/bwrap — bubblewrap
34. https://github.com/containers/bubblewrap/issues/591 — SDL udev in sandbox
35. https://wiki.libsdl.org/SDL3/EnvironmentVariables — SDL hints
36. https://github.com/KarsMulder/evsieve — evdev grab and re-emit
37. https://docs.kernel.org/input/uinput.html — uinput
38. https://dolphin-emu.org/blog/2021/07/21/integrated-gba/ — Integrated GBA
39. https://raw.githubusercontent.com/dolphin-emu/dolphin/master/Source/Core/DolphinQt/GBAWidget.cpp — GBA windows
40. https://github.com/dolphin-emu/dolphin/pull/13286 — xcb forced on Wayland
41. https://github.com/batocera-linux/batocera.linux/pull/7531 — ratpoison GBA layout

## Methodology

Searched 30+ queries across WebSearch, DuckDuckGo and Brave via the web-search MCP, plus `gh search
repos` and the GitHub API for repo metadata, trees and source. Deep-read 12 sources in full
(PartyDeck README and `src/launch.rs`, Splinux and CouchPlay READMEs, gamescope `main.cpp`,
Dolphin `GBAWidget.cpp`/`Main.cpp`, DualScope gist, wlroots env docs, sway man page). Three parallel
research agents covered: (1) existing tools, (2) compositor/input primitives, (3) Four Swords
Adventures/Dolphin. Claims from a single source are marked as such.
