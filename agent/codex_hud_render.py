#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import re
import sys
import unicodedata
from dataclasses import dataclass
from typing import Final

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    __package__ = "agent"
from .codex_hud_types import ChildAgentFacts, MemoryFacts, Snapshot

TMUX_GREEN: Final = "#[fg=colour114]"
TMUX_AMBER: Final = "#[fg=colour208]"
TMUX_RED: Final = "#[fg=colour203]"
TMUX_DIM: Final = "#[fg=colour245]"
TMUX_RESET: Final = "#[default]"
ANSI_RESET: Final = "\033[0m"
ANSI_AMBER: Final = "\033[38;5;208m"
ANSI_DIM: Final = "\033[38;5;245m"
CONTROL_RE: Final = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class Part:
    label: str
    value: str
    color: str
    priority: int


def sanitize_plain(value: str | None) -> str:
    raw = value or ""
    clean = CONTROL_RE.sub("", raw.replace("\n", " ").replace("\r", " "))
    return " ".join(clean.replace("#[", "[").replace("#(", "(").split())


def sanitize_tmux(value: str | None) -> str:
    return sanitize_plain(value).replace("#", "##")


def display_width(text: str) -> int:
    width = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1
    return width


def clip(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if display_width(text) <= width:
        return text
    marker = "..."
    if width <= len(marker):
        return "." * width
    limit = width - len(marker)
    used = 0
    chars: list[str] = []
    for char in text:
        char_width = 0 if unicodedata.combining(char) else 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1
        if used + char_width > limit:
            break
        chars.append(char)
        used += char_width
    return "".join(chars) + marker


def _compact_int(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1000:
        return f"{value // 1000}k"
    return str(value)


def _age(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    return f"{int(seconds // 3600)}h ago"


def _limit_text(percent: float | None) -> str | None:
    return f"{percent:.0f}% used" if percent is not None else None


def _percent_text(percent: float | None) -> str | None:
    return f"{percent:.0f}%" if percent is not None else None


def _context_remaining(snapshot: Snapshot) -> float | None:
    if snapshot.context.used_percent is None:
        return None
    return max(0.0, 100.0 - snapshot.context.used_percent)


def _usage_parts(snapshot: Snapshot) -> list[Part]:
    parts: list[Part] = []
    remaining = _context_remaining(snapshot)
    if remaining is not None:
        parts.append(Part("ctx", f"{remaining:.0f}% left", TMUX_RED if remaining <= 15 else TMUX_AMBER, 5))
    primary = _limit_text(snapshot.limits.primary_used_percent)
    if primary:
        parts.append(Part(_primary_limit_label(snapshot), primary, TMUX_AMBER, 5))
    weekly = _limit_text(snapshot.limits.weekly_used_percent)
    if weekly:
        parts.append(Part("week", weekly, TMUX_AMBER, 5))
    if snapshot.usage.total_tokens is not None:
        parts.append(Part("tok", _compact_int(snapshot.usage.total_tokens), TMUX_DIM, 4))
    if snapshot.usage.cache_ratio_percent is not None:
        ratio = snapshot.usage.cache_ratio_percent
        color = TMUX_GREEN if ratio >= 90 else TMUX_AMBER if ratio >= 70 else TMUX_RED
        parts.append(Part("cache", f"{ratio:.0f}%", color, 3))
    model = sanitize_plain(snapshot.session.model)
    if model:
        parts.append(Part("model", model, TMUX_DIM, 2))
    return parts


def _activity_parts(snapshot: Snapshot) -> list[Part]:
    parts = [Part("session", snapshot.session.status, TMUX_GREEN if snapshot.session.status == "ready" else TMUX_RED, 3)]
    if snapshot.children:
        parts.append(Part("agents", f"{len(snapshot.children)} shown", TMUX_DIM, 2))
    if snapshot.tasks.active is not None and snapshot.tasks.total is not None:
        parts.append(Part("tasks", f"{snapshot.tasks.active}/{snapshot.tasks.total}", TMUX_GREEN if snapshot.tasks.active else TMUX_DIM, 2))
    observed = _age(snapshot.session.updated_age_seconds)
    if observed:
        parts.append(Part("obs", observed, TMUX_DIM, 5))
    recent = sanitize_plain(snapshot.recent_tool.name)
    age = _age(snapshot.recent_tool.age_seconds)
    if recent:
        parts.append(Part("tool", f"{recent}{f' {age}' if age else ''}", TMUX_DIM, 1))
    if snapshot.memory.health != "ready":
        parts.append(Part("mem", _memory_text(snapshot.memory), TMUX_RED, 3))
    elif snapshot.memory.recall == "available" or snapshot.memory.save == "available":
        parts.append(Part("mem", _memory_text(snapshot.memory), TMUX_GREEN, 2))
    if snapshot.omx.status != "unavailable":
        parts.append(Part("OMX", snapshot.omx.status, TMUX_DIM, 1))
    if snapshot.omx.workflows:
        parts.append(Part("OMX", ",".join(snapshot.omx.workflows), TMUX_DIM, 1))
    return parts


def _memory_text(memory: MemoryFacts) -> str:
    recall = "observed" if memory.recall == "available" else "not observed"
    save = "observed" if memory.save == "available" else "not observed"
    return f"{memory.health}/recall:{recall}/save:{save}"


def _tmux_part(part: Part) -> str:
    return f"{TMUX_DIM}{sanitize_tmux(part.label)} {part.color}{sanitize_tmux(part.value)}{TMUX_RESET}"


def _ansi_part(part: Part, color: bool) -> str:
    if not color:
        return f"{sanitize_plain(part.label)} {sanitize_plain(part.value)}"
    ansi = {TMUX_GREEN: "\033[38;5;114m", TMUX_AMBER: ANSI_AMBER, TMUX_RED: "\033[38;5;203m"}.get(part.color, ANSI_DIM)
    return f"{ANSI_DIM}{sanitize_plain(part.label)} {ansi}{sanitize_plain(part.value)}{ANSI_RESET}"


def _chosen_parts(snapshot: Snapshot, width: int) -> list[Part]:
    ordered = sorted(_usage_parts(snapshot) + _activity_parts(snapshot), key=lambda part: -part.priority)
    chosen: list[Part] = []
    for part in ordered:
        candidate = chosen + [part]
        plain = " | ".join(f"{item.label} {item.value}" for item in candidate)
        if display_width(plain) <= width or not chosen:
            chosen = candidate
    return chosen


def render_status(snapshot: Snapshot, width: int) -> str:
    chosen = _chosen_parts(snapshot, width)
    plain_line = "  ".join(f"{part.label} {part.value}" for part in chosen)
    if display_width(plain_line) > width:
        return sanitize_tmux(clip(plain_line, width))
    return "  ".join(_tmux_part(part) for part in chosen)


def render_status_plain(snapshot: Snapshot, width: int, color: bool) -> str:
    chosen = _chosen_parts(snapshot, width)
    plain_line = "  ".join(f"{part.label} {part.value}" for part in chosen)
    if display_width(plain_line) > width:
        return clip(plain_line, width)
    return "  ".join(_ansi_part(part, color) for part in chosen)


def _line(label: str, value: str | float | None) -> str | None:
    if isinstance(value, int | float):
        clean = f"{value:.1f}" if isinstance(value, float) and value % 1 else str(int(value))
    else:
        clean = sanitize_plain(value)
    return f"{ANSI_DIM}{label:<18}{ANSI_RESET} {clean}" if clean else None


def _child_line(child: ChildAgentFacts) -> str:
    age = _age(child.updated_age_seconds)
    bits = [child.label, f"edge:{child.status}"]
    if child.model:
        bits.append(child.model)
    if child.reasoning_effort:
        bits.append(child.reasoning_effort)
    if age:
        bits.append(age)
    return " - " + " / ".join(sanitize_plain(bit) for bit in bits if bit)


def render_detail(snapshot: Snapshot, color: bool = True) -> str:
    rows: list[str] = [_heading("Codex HUD", color), ""]
    usage = [
        _line("context remaining", _percent_text(_context_remaining(snapshot))),
        _line("context used", _percent_text(snapshot.context.used_percent)),
        _line("context window", snapshot.context.window_tokens),
        _line(f"{_primary_limit_label(snapshot)}/primary limit", _limit_text(snapshot.limits.primary_used_percent)),
        _line("weekly limit", _limit_text(snapshot.limits.weekly_used_percent)),
        _line("used tokens", snapshot.usage.total_tokens),
        _line("input/output", _input_output(snapshot)),
        _line("cache hit", _percent_text(snapshot.usage.cache_ratio_percent)),
    ]
    rows.extend([_section("Usage", color), *[row for row in usage if row], ""])
    rows.extend([_section("Activity", color), *(_child_line(child) for child in snapshot.children)])
    if not snapshot.children:
        rows.append("agents: none reported")
    task_line = _task_text(snapshot)
    rows.append(_line("tasks", task_line) or "")
    tool = _line("recent tool", _tool_text(snapshot))
    if tool:
        rows.append(tool)
    rows.append(_line("OMX", snapshot.omx.status) or "")
    if snapshot.omx.workflows:
        rows.append(_line("workflows", ", ".join(sanitize_plain(item) for item in snapshot.omx.workflows)) or "")
    rows.append("")
    rows.extend([_section("Health", color), _line("memory", _memory_text(snapshot.memory)) or "", ""])
    metadata = [
        _line("session", snapshot.session.thread_id),
        _line("status", snapshot.session.status),
        _line("model", snapshot.session.model),
        _line("reasoning", snapshot.session.reasoning_effort),
        _line("observed", _age(snapshot.session.updated_age_seconds)),
        _line("sources", ", ".join(sanitize_plain(source) for source in snapshot.sources) or "none"),
        _line("transcript", snapshot.session.transcript_path) or _line("transcript", "unknown"),
    ]
    rows.extend([_section("Metadata", color), *[row for row in metadata if row]])
    text = "\n".join(rows).rstrip() + "\n"
    return text if color else CONTROL_RE.sub("", text)


def _input_output(snapshot: Snapshot) -> str | None:
    if snapshot.usage.input_tokens is None and snapshot.usage.output_tokens is None:
        return None
    return f"{snapshot.usage.input_tokens or 0}/{snapshot.usage.output_tokens or 0}"


def _tool_text(snapshot: Snapshot) -> str | None:
    name = sanitize_plain(snapshot.recent_tool.name)
    if not name:
        return None
    age = _age(snapshot.recent_tool.age_seconds)
    return f"{name}{f' ({age})' if age else ''}"


def _task_text(snapshot: Snapshot) -> str | None:
    if snapshot.tasks.active is None and snapshot.tasks.total is None:
        return snapshot.tasks.status
    return f"{snapshot.tasks.active or 0}/{snapshot.tasks.total or 0} ({snapshot.tasks.status})"


def _primary_limit_label(snapshot: Snapshot) -> str:
    return "5h" if snapshot.limits.primary_window_minutes == 300 else "limit"


def _heading(label: str, color: bool) -> str:
    return f"{ANSI_AMBER}{label}{ANSI_RESET}" if color else label


def _section(label: str, color: bool) -> str:
    return _heading(label, color)
