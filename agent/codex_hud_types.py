from dataclasses import dataclass
from typing import Literal, TypeAlias

SessionStatus: TypeAlias = Literal["ready", "unknown", "missing", "malformed"]
MemoryHealth: TypeAlias = Literal["ready", "down"]
CapabilityStatus: TypeAlias = Literal["available", "unavailable"]
OmxStatus: TypeAlias = Literal["active", "idle", "unavailable"]
TaskStatus: TypeAlias = Literal["available", "unavailable"]


@dataclass(frozen=True, slots=True)
class UsageTotals:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    cache_write_input_tokens: int | None = None
    reasoning_output_tokens: int | None = None
    total_tokens: int | None = None
    cache_ratio_percent: float | None = None


@dataclass(frozen=True, slots=True)
class ContextFacts:
    window_tokens: int | None = None
    used_percent: float | None = None


@dataclass(frozen=True, slots=True)
class LimitFacts:
    primary_used_percent: float | None = None
    primary_window_minutes: int | None = None
    primary_resets_at: int | None = None
    weekly_used_percent: float | None = None


@dataclass(frozen=True, slots=True)
class SessionFacts:
    status: SessionStatus
    thread_id: str | None = None
    transcript_path: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    updated_age_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class ChildAgentFacts:
    thread_id: str
    label: str
    status: str
    model: str | None
    reasoning_effort: str | None
    updated_age_seconds: float | None


@dataclass(frozen=True, slots=True)
class ToolFacts:
    name: str | None = None
    age_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class MemoryFacts:
    health: MemoryHealth
    recall: CapabilityStatus
    save: CapabilityStatus


@dataclass(frozen=True, slots=True)
class OmxFacts:
    status: OmxStatus = "unavailable"
    workflows: tuple[str, ...] = ()
    metrics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TaskFacts:
    status: TaskStatus = "unavailable"
    active: int | None = None
    total: int | None = None


@dataclass(frozen=True, slots=True)
class ParsedRollout:
    session: SessionFacts
    usage: UsageTotals
    context: ContextFacts
    limits: LimitFacts
    recent_tool: ToolFacts


@dataclass(frozen=True, slots=True)
class Snapshot:
    session: SessionFacts
    usage: UsageTotals
    context: ContextFacts
    limits: LimitFacts
    children: tuple[ChildAgentFacts, ...]
    recent_tool: ToolFacts
    memory: MemoryFacts
    omx: OmxFacts
    tasks: TaskFacts
    sources: tuple[str, ...]
