"""Tiny stand-in for "any multiplayer game".

Each process is one player. State is shared over localhost UDP so every
window shows every player. Input: first gamepad SDL can see, else keyboard
(arrows/WASD). The HUD prints which gamepads this instance can see, which
makes input isolation visible at a glance.

    python3 game.py --player 1 [--role main|pad] [--players 4]
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time

os.environ.setdefault("SDL_VIDEO_ALLOW_SCREENSAVER", "1")
import pygame  # noqa: E402

BASE_PORT = 41000
COLORS = [(230, 70, 70), (70, 130, 230), (70, 200, 90), (240, 200, 60), (200, 90, 220)]
SPEED = 4.0
DEADZONE = 0.25


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--player", type=int, required=True, help="1-based player index")
    ap.add_argument("--players", type=int, default=5, help="max players to listen for")
    ap.add_argument("--role", choices=["main", "pad"], default="main",
                    help="main draws everyone, pad draws only itself (GBA-style)")
    ap.add_argument("--size", default="640x360")
    return ap.parse_args(argv)


def read_axis(joy: pygame.joystick.JoystickType | None, keys) -> tuple[float, float]:
    dx = dy = 0.0
    if joy is not None:
        ax, ay = joy.get_axis(0), joy.get_axis(1)
        if joy.get_numhats():
            hx, hy = joy.get_hat(0)
            ax, ay = ax or hx, ay or -hy
        dx = ax if abs(ax) > DEADZONE else 0.0
        dy = ay if abs(ay) > DEADZONE else 0.0
    dx += (keys[pygame.K_RIGHT] or keys[pygame.K_d]) - (keys[pygame.K_LEFT] or keys[pygame.K_a])
    dy += (keys[pygame.K_DOWN] or keys[pygame.K_s]) - (keys[pygame.K_UP] or keys[pygame.K_w])
    return max(-1.0, min(1.0, dx)), max(-1.0, min(1.0, dy))


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    w, h = (int(v) for v in args.size.split("x"))
    pygame.init()
    pygame.joystick.init()
    screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
    pygame.display.set_caption(f"dummy game - player {args.player} ({args.role})")
    font = pygame.font.SysFont(None, 22)
    clock = pygame.time.Clock()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    sock.bind(("127.0.0.1", BASE_PORT + args.player))
    peers = [("127.0.0.1", BASE_PORT + i) for i in range(1, args.players + 1) if i != args.player]

    pos = [0.5, 0.5]  # normalised so every window size agrees on world coords
    others: dict[int, tuple[float, float, float]] = {}
    joy = None
    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                running = False
        if joy is None and pygame.joystick.get_count():
            joy = pygame.joystick.Joystick(0)
            joy.init()
        dx, dy = read_axis(joy, pygame.key.get_pressed())
        pos = [min(1.0, max(0.0, pos[0] + dx * SPEED / 640)), min(1.0, max(0.0, pos[1] + dy * SPEED / 360))]

        msg = json.dumps({"p": args.player, "x": pos[0], "y": pos[1]}).encode()
        for peer in peers:
            try:
                sock.sendto(msg, peer)
            except OSError:
                pass
        while True:
            try:
                data, _ = sock.recvfrom(256)
            except (BlockingIOError, OSError):
                break
            try:
                d = json.loads(data)
                others = {**others, d["p"]: (d["x"], d["y"], time.monotonic())}
            except (ValueError, KeyError):
                pass

        sw, sh = screen.get_size()
        screen.fill((24, 24, 32) if args.role == "main" else (40, 48, 40))
        now = time.monotonic()
        if args.role == "main":
            for pid, (x, y, seen) in others.items():
                if now - seen < 2.0:
                    pygame.draw.rect(screen, COLORS[(pid - 1) % len(COLORS)], (x * (sw - 40), y * (sh - 40), 40, 40), border_radius=6)
        pygame.draw.rect(screen, COLORS[(args.player - 1) % len(COLORS)], (pos[0] * (sw - 40), pos[1] * (sh - 40), 40, 40), border_radius=6)
        pads = [pygame.joystick.Joystick(i).get_name() for i in range(pygame.joystick.get_count())]
        lines = [f"player {args.player}  role={args.role}  {sw}x{sh}",
                 f"pads visible: {pads or 'none (keyboard)'}",
                 f"peers alive: {sorted(p for p, (_, _, s) in others.items() if now - s < 2.0)}"]
        for i, line in enumerate(lines):
            screen.blit(font.render(line, True, (230, 230, 230)), (8, 8 + 20 * i))
        pygame.display.flip()
        clock.tick(60)
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
