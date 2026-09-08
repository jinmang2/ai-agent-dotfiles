#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, assert_never

import tomllib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts.codex_wiring_hooks import render_hooks
from scripts.codex_wiring_toml import render_config


@dataclass(frozen=True, slots=True)
class Wiring:
    config_text: str
    hooks_text: str
    unsupported_hook_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CliArgs:
    mode: Literal["check", "apply"]
    codex_home: pathlib.Path
    workflow_owner: Literal["omx"] | None


def load_wiring(codex_home: pathlib.Path, workflow_owner: Literal["omx"] | None) -> Wiring:
    config_path = codex_home / "config.toml"
    hooks_path = codex_home / "hooks.json"
    try:
        config_text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
        tomllib.loads(config_text) if config_text.strip() else {}
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeError(f"invalid config.toml: {exc}") from exc
    try:
        hooks_text = hooks_path.read_text(encoding="utf-8") if hooks_path.exists() else "{}\n"
        rendered_hooks, unsupported = render_hooks(hooks_text)
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise RuntimeError(f"invalid hooks.json: {exc}") from exc
    return Wiring(
        config_text=render_config(config_text, workflow_owner, codex_home, hooks_text),
        hooks_text=rendered_hooks,
        unsupported_hook_keys=unsupported,
    )


def backup_file(path: pathlib.Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.bak-{stamp}")
    shutil.copy2(path, backup)
    os.chmod(backup, 0o600)


def write_if_changed(path: pathlib.Path, text: str) -> bool:
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current == text:
        return False
    backup_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def check(codex_home: pathlib.Path, workflow_owner: Literal["omx"] | None) -> int:
    try:
        wiring = load_wiring(codex_home, workflow_owner)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    drift = False
    config_path = codex_home / "config.toml"
    hooks_path = codex_home / "hooks.json"
    current_config = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    current_hooks = hooks_path.read_text(encoding="utf-8") if hooks_path.exists() else "{}\n"
    if current_config != wiring.config_text:
        print("would update config.toml")
        drift = True
    if current_hooks != wiring.hooks_text:
        print("would update hooks.json")
        drift = True
    if wiring.unsupported_hook_keys:
        print(f"unsupported hooks.json top-level keys: {', '.join(wiring.unsupported_hook_keys)}")
        drift = True
    return 1 if drift else 0


def apply(codex_home: pathlib.Path, workflow_owner: Literal["omx"] | None) -> int:
    try:
        wiring = load_wiring(codex_home, workflow_owner)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if wiring.unsupported_hook_keys:
        keys = ", ".join(wiring.unsupported_hook_keys)
        print(f"refusing to apply unsupported hooks.json top-level keys: {keys}", file=sys.stderr)
        return 2
    config_changed = write_if_changed(codex_home / "config.toml", wiring.config_text)
    hooks_changed = write_if_changed(codex_home / "hooks.json", wiring.hooks_text)
    changed = [name for name, value in (("config.toml", config_changed), ("hooks.json", hooks_changed)) if value]
    print("updated " + ", ".join(changed) if changed else "codex wiring already current")
    return 0


def parse_args(argv: list[str]) -> CliArgs:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--codex-home", type=pathlib.Path)
    target.add_argument("--live", action="store_true")
    parser.add_argument("--workflow-owner", choices=("omx",))
    namespace = parser.parse_args(argv)
    codex_home = pathlib.Path.home() / ".codex" if namespace.live else namespace.codex_home
    mode_name: Literal["check", "apply"] = "apply" if namespace.apply else "check"
    return CliArgs(mode=mode_name, codex_home=codex_home, workflow_owner=namespace.workflow_owner)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    match args.mode:
        case "check":
            return check(args.codex_home, args.workflow_owner)
        case "apply":
            return apply(args.codex_home, args.workflow_owner)
        case unreachable:
            assert_never(unreachable)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
