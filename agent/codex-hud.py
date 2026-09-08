#!/usr/bin/env python3
from __future__ import annotations

import getopt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from typing import Final, Literal, TypeAlias

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    __package__ = "agent"
from .codex_hud_data import collect_snapshot
from .codex_hud_render import render_detail, render_status, render_status_plain

CliMode: TypeAlias = Literal["once", "watch", "status", "detail"]
HELP: Final = (
    "usage: codex-hud.py [--status | --detail | --once | --watch] [options]\n\n"
    "Compact local Codex companion HUD.\n\n"
    "options:\n"
    "  --status              print one tmux-status formatted line\n"
    "  --detail              print multiline popup detail\n"
    "  --json                print snapshot JSON\n"
    "  --pane PANE           source pane/session identity\n"
    "  --width WIDTH         render width for --status/--once\n"
    "  --no-color            compatibility no-op for --status\n"
    "  --interval SECONDS    compatibility for --watch\n"
    "  --parent-pane PANE    compatibility alias for --pane\n"
    "  -h, --help\n"
)


def _parent_alive(pane: str | None) -> bool:
    if pane is None:
        return True
    check = os.environ.get("CODEX_HUD_PARENT_CHECK")
    command = [check, pane] if check else ["tmux", "display-message", "-p", "-t", pane, "#{pane_id}"]
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=0.2, check=False).returncode == 0
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired):
        return False


def _collector_cwd(pane: str | None) -> pathlib.Path:
    if pane is None:
        return pathlib.Path.cwd()
    try:
        result = subprocess.run(["tmux", "display-message", "-p", "-t", pane, "#{pane_current_path}"], capture_output=True, text=True, timeout=0.2, check=False)
    except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired):
        return pathlib.Path.cwd()
    value = result.stdout.strip()
    return pathlib.Path(value) if result.returncode == 0 and value else pathlib.Path.cwd()


def _parse(argv: list[str]) -> tuple[CliMode, bool, bool, int | None, float, str | None, bool]:
    mode: CliMode = "once"
    json_output = False
    color = True
    width: int | None = None
    interval = 1.0
    pane: str | None = None
    try:
        options, extras = getopt.getopt(argv, "h", ["help", "once", "watch", "status", "detail", "json", "no-color", "width=", "interval=", "parent-pane=", "pane="])
    except getopt.GetoptError as exc:
        raise SystemExit(str(exc)) from exc
    if extras:
        raise SystemExit(f"unexpected arguments: {' '.join(extras)}")
    for option, value in options:
        match option:
            case "-h" | "--help":
                return mode, json_output, color, width, interval, pane, True
            case "--once":
                mode = "once"
            case "--watch":
                mode = "watch"
            case "--status":
                mode = "status"
            case "--detail":
                mode = "detail"
            case "--json":
                json_output = True
            case "--no-color":
                color = False
            case "--width":
                width = int(value)
                if width <= 0:
                    raise SystemExit("--width must be positive")
            case "--interval":
                interval = float(value)
                if interval <= 0:
                    raise SystemExit("--interval must be positive")
            case "--parent-pane" | "--pane":
                pane = value
            case _:
                raise SystemExit(f"unknown option: {option}")
    return mode, json_output, color, width, interval, pane, False


def _width(value: int | None) -> int:
    return value if value is not None else shutil.get_terminal_size((80, 20)).columns


def main(argv: list[str]) -> int:
    mode, json_output, color, width, interval, pane, help_requested = _parse(argv)
    if help_requested:
        sys.stdout.write(HELP)
        return 0
    cwd = _collector_cwd(pane)
    snapshot = collect_snapshot(pane=pane, cwd=cwd)
    if json_output:
        print(json.dumps(asdict(snapshot), ensure_ascii=False, sort_keys=True))
        return 0
    if mode == "detail":
        sys.stdout.write(render_detail(snapshot, color))
        return 0
    if mode == "watch":
        while _parent_alive(pane):
            sys.stdout.write("\033[H\033[J")
            current = collect_snapshot(pane=pane, cwd=cwd)
            sys.stdout.write(render_status_plain(current, _width(width), color))
            sys.stdout.flush()
            time.sleep(max(0.01, interval))
        return 0
    line = render_status(snapshot, _width(width)) if mode == "status" else render_status_plain(snapshot, _width(width), color)
    sys.stdout.write(line + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
