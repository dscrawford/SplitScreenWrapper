{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShell {
  packages = with pkgs; [
    (python3.withPackages (ps: [ ps.pygame-ce ps.evdev ps.i3ipc ps.pytest ]))
    bubblewrap sway gamescope grim
  ];
}
