import json
import os
import pathlib
import subprocess
import sys
from datetime import UTC, datetime
from typing import Final, TypeAlias
from urllib import error, request

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    __package__ = "agent"
from .codex_hud_sqlite import children_for, thread_facts
from .codex_hud_types import (
    ContextFacts,
    LimitFacts,
    MemoryFacts,
    OmxFacts,
    ParsedRollout,
    SessionFacts,
    Snapshot,
    TaskFacts,
    ToolFacts,
    UsageTotals,
)

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonMap: TypeAlias = dict[str, JsonValue]
TAIL_BYTES: Final = 524_288


def collect_snapshot(pane: str | None, cwd: pathlib.Path) -> Snapshot:
    session_id = tmux_option(pane, "@codex_hud_session")
    transcript = tmux_option(pane, "@codex_hud_transcript")
    codex_home = codex_home_from_pane(pane)
    db_facts = thread_facts(session_id, codex_home) if session_id is not None else None
    if transcript is None and session_id is not None:
        transcript = db_facts.rollout_path if db_facts is not None else None
    memory = collect_memory()
    omx = collect_omx(session_id, cwd)
    if session_id is None:
        return Snapshot(SessionFacts("unknown"), UsageTotals(), ContextFacts(), LimitFacts(), (), ToolFacts(), memory, omx, TaskFacts(), ("pane",))
    if transcript is None:
        return Snapshot(SessionFacts("unknown", thread_id=session_id), UsageTotals(), ContextFacts(), LimitFacts(), (), ToolFacts(), memory, omx, TaskFacts(), ("pane",))
    path = pathlib.Path(transcript).expanduser()
    if not path.is_file():
        return Snapshot(SessionFacts("missing", thread_id=session_id, transcript_path=str(path)), UsageTotals(), ContextFacts(), LimitFacts(), (), ToolFacts(), memory, omx, TaskFacts(), ("pane", str(path)))
    parsed = parse_rollout(path)
    if parsed is None:
        return Snapshot(SessionFacts("malformed", thread_id=session_id, transcript_path=str(path)), UsageTotals(), ContextFacts(), LimitFacts(), (), ToolFacts(), memory, omx, TaskFacts(), ("pane", str(path)))
    if session_id is not None and parsed.session.thread_id != session_id:
        return Snapshot(SessionFacts("malformed", thread_id=session_id, transcript_path=str(path)), UsageTotals(), ContextFacts(), LimitFacts(), (), ToolFacts(), memory, omx, TaskFacts(), ("pane", str(path), "session-mismatch"))
    thread_id = parsed.session.thread_id or session_id
    model = parsed.session.model or db_facts.model if db_facts is not None else parsed.session.model
    effort = parsed.session.reasoning_effort or db_facts.reasoning_effort if db_facts is not None else parsed.session.reasoning_effort
    session = SessionFacts("ready", thread_id, str(path), model, effort, parsed.session.updated_age_seconds)
    return Snapshot(session, parsed.usage, parsed.context, parsed.limits, children_for(thread_id, codex_home), parsed.recent_tool, memory, omx, TaskFacts(), ("pane", str(path), str(codex_home)))


def tmux_option(pane: str | None, option: str) -> str | None:
    if pane is None:
        return None
    try:
        result = subprocess.run(["tmux", "show-options", "-p", "-t", pane, "-v", option], capture_output=True, text=True, timeout=0.2, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def codex_home_from_pane(pane: str | None) -> pathlib.Path:
    value = tmux_option(pane, "@codex_hud_home") or os.environ.get("CODEX_HOME") or str(pathlib.Path.home() / ".codex")
    return pathlib.Path(value).expanduser()


def parse_rollout(path: pathlib.Path) -> ParsedRollout | None:
    try:
        lines = selected_rollout_lines(path)
        first = first_json_line(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if first is not None:
        lines = (first, *lines)
    session = SessionFacts("ready")
    usage = UsageTotals()
    context = ContextFacts()
    limits = LimitFacts()
    tool = ToolFacts()
    for row in lines:
        payload = map_value(row.get("payload"))
        timestamp = text_value(row.get("timestamp"))
        match text_value(row.get("type")):
            case "session_meta":
                session = session_from_meta(payload, timestamp)
            case "turn_context":
                session = merge_turn_context(session, payload, timestamp)
            case "event_msg":
                usage, context, limits = token_count_facts(payload, usage, context, limits)
                if text_value(payload.get("type")) == "token_count":
                    session = session_with_age(session, timestamp)
                tool = tool_from_event(payload, timestamp, tool)
            case "response_item":
                tool = tool_from_response(payload, timestamp, tool)
            case "token_usage_record":
                usage = usage_from_map(map_value(payload.get("thread_token_usage")) or map_value(payload.get("turn_token_usage")) or usage)
            case _:
                pass
    return ParsedRollout(session, usage, context, limits, tool)


def selected_rollout_lines(path: pathlib.Path) -> tuple[JsonMap, ...]:
    with path.open("rb") as handle:
        size = path.stat().st_size
        if size > TAIL_BYTES:
            handle.seek(size - TAIL_BYTES)
            _ = handle.readline()
        raw = handle.read().decode("utf-8")
    rows: list[JsonMap] = []
    lines = [line for line in raw.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            if index == len(lines) - 1:
                continue
            raise
        if isinstance(value, dict):
            rows.append(value)
        elif index != len(lines) - 1:
            raise json.JSONDecodeError("expected object", line, 0)
    return tuple(rows)


def first_json_line(path: pathlib.Path) -> JsonMap | None:
    with path.open("r", encoding="utf-8") as handle:
        line = handle.readline().strip()
    if not line:
        return None
    value = json.loads(line)
    if not isinstance(value, dict):
        raise json.JSONDecodeError("expected object", line, 0)
    return value


def session_from_meta(payload: JsonMap, timestamp: str | None) -> SessionFacts:
    model = text_value(payload.get("model"))
    return SessionFacts("ready", text_value(payload.get("id")), None, model, text_value(payload.get("reasoning_effort")), age(timestamp))


def merge_turn_context(session: SessionFacts, payload: JsonMap, timestamp: str | None) -> SessionFacts:
    model = text_value(payload.get("model")) or session.model
    effort = text_value(payload.get("effort")) or text_value(payload.get("reasoning_effort")) or session.reasoning_effort
    return SessionFacts(session.status, session.thread_id, session.transcript_path, model, effort, age(timestamp) or session.updated_age_seconds)


def session_with_age(session: SessionFacts, timestamp: str | None) -> SessionFacts:
    return SessionFacts(session.status, session.thread_id, session.transcript_path, session.model, session.reasoning_effort, age(timestamp) or session.updated_age_seconds)


def token_count_facts(payload: JsonMap, usage: UsageTotals, context: ContextFacts, limits: LimitFacts) -> tuple[UsageTotals, ContextFacts, LimitFacts]:
    if text_value(payload.get("type")) != "token_count":
        return usage, context, limits
    info = map_value(payload.get("info"))
    rate = map_value(payload.get("rate_limits"))
    next_usage = usage_from_map(map_value(info.get("total_token_usage")) or usage)
    last_map = map_value(info.get("last_token_usage"))
    window = int_value(info.get("model_context_window"))
    total = int_value(last_map.get("total_tokens")) if last_map else None
    used = round(total / window * 100, 1) if total is not None and window else None
    return next_usage, ContextFacts(window, used), limits_from_map(rate) if rate else limits


def usage_from_map(data: JsonMap | UsageTotals) -> UsageTotals:
    if isinstance(data, UsageTotals):
        return data
    input_tokens = int_value(data.get("input_tokens"))
    cached = int_value(data.get("cached_input_tokens"))
    ratio = round(cached / input_tokens * 100, 1) if input_tokens and cached is not None else None
    return UsageTotals(input_tokens, int_value(data.get("output_tokens")), cached, int_value(data.get("cache_write_input_tokens")), int_value(data.get("reasoning_output_tokens")), int_value(data.get("total_tokens")), ratio)


def limits_from_map(data: JsonMap) -> LimitFacts:
    primary = map_value(data.get("primary"))
    secondary = map_value(data.get("secondary"))
    weekly = number_value(secondary.get("used_percent")) if secondary and int_value(secondary.get("window_minutes")) == 10080 else None
    return LimitFacts(number_value(primary.get("used_percent")) if primary else None, int_value(primary.get("window_minutes")) if primary else None, int_value(primary.get("resets_at")) if primary else None, weekly)


def tool_from_event(payload: JsonMap, timestamp: str | None, current: ToolFacts) -> ToolFacts:
    item = map_value(payload.get("item"))
    name = text_value(item.get("type")) if item else None
    return ToolFacts(name, age(timestamp)) if name else current


def tool_from_response(payload: JsonMap, timestamp: str | None, current: ToolFacts) -> ToolFacts:
    name = text_value(payload.get("name"))
    return ToolFacts(name, age(timestamp)) if name else current


def collect_memory() -> MemoryFacts:
    base = os.environ.get("AGMEM_DAEMON_URL", "http://127.0.0.1:8765").rstrip("/")
    try:
        with request.urlopen(request.Request(f"{base}/health", method="GET"), timeout=0.2) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (error.URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return MemoryFacts("down", "unavailable", "unavailable")
    ok = isinstance(value, dict) and value.get("ok") is True
    return MemoryFacts("ready" if ok else "down", "unavailable", "unavailable")


def collect_omx(session_id: str | None, cwd: pathlib.Path) -> OmxFacts:
    if session_id is None:
        return OmxFacts()
    try:
        result = subprocess.run(["omx", "hud", "--json"], cwd=cwd, capture_output=True, text=True, timeout=0.5, check=False)
        value = json.loads(result.stdout or "{}") if result.returncode == 0 else {}
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return OmxFacts()
    if not isinstance(value, dict):
        return OmxFacts()
    payload: JsonMap = value
    session = map_value(payload.get("session"))
    payload_session = text_value(session.get("session_id"))
    payload_cwd = text_value(session.get("cwd"))
    if payload_session != session_id or payload_cwd != str(cwd):
        return OmxFacts()
    workflows = tuple(key for key in ("ultrawork", "autopilot", "ultragoal", "ralph", "team") if isinstance(payload.get(key), dict))
    return OmxFacts("active" if workflows else "idle", workflows, ())


def map_value(value: JsonValue) -> JsonMap:
    return value if isinstance(value, dict) else {}


def text_value(value: JsonValue) -> str | None:
    return value if isinstance(value, str) and value else None


def int_value(value: JsonValue) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def number_value(value: JsonValue) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def age(timestamp: str | None) -> float | None:
    if timestamp is None:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return max(0.0, datetime.now(UTC).timestamp() - parsed.astimezone(UTC).timestamp())
