"""Translate raw crewAI callback objects into UI-friendly events.

Two source layers feed the same events list:
  1. `Crew(step_callback=..., task_callback=...)` — coarse step/task boundaries.
  2. `crewai_event_bus` subscriptions (in routes/posts.py) — fine-grained tool
     calls, tool results, agent boundaries, reasoning plans.

crewAI's callback / event object types vary across versions; we read defensively
and fall back to `str(obj)` for anything we don't recognise. Each event is small,
plain-JSON, and capped in length so polling stays cheap.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Callable

EVENT_TEXT_CAP = 800
EVENT_LIST_CAP = 120


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(text: str, cap: int = EVENT_TEXT_CAP) -> str:
    text = (text or "").strip()
    if len(text) <= cap:
        return text
    return text[: cap - 1] + "…"


def _agent_label(obj: Any) -> str:
    for attr in ("agent", "agent_role", "role"):
        val = getattr(obj, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if val is not None:
            inner = getattr(val, "role", None)
            if isinstance(inner, str) and inner.strip():
                return inner.strip()
    return ""


def event_from_step(step: Any) -> dict[str, Any]:
    """Format an arbitrary crewAI step output for UI consumption."""
    cls = type(step).__name__

    # Tool call planned
    tool = getattr(step, "tool", None)
    tool_input = getattr(step, "tool_input", None)
    if tool:
        text = f"calling tool `{tool}`"
        if tool_input:
            text += f" with {_truncate(str(tool_input), 200)}"
        return _event("tool", _agent_label(step), text, cls=cls)

    # Tool result
    if cls.lower().startswith("toolresult") or cls.lower() == "toolusage":
        result_text = getattr(step, "result", None) or getattr(step, "output", None) or str(step)
        return _event("tool_result", _agent_label(step), _truncate(str(result_text)), cls=cls)

    # Final agent answer (AgentFinish)
    return_values = getattr(step, "return_values", None)
    if return_values:
        out = return_values.get("output") if isinstance(return_values, dict) else None
        return _event("answer", _agent_label(step), _truncate(str(out or return_values)), cls=cls)

    # Plain log / thought
    log = getattr(step, "log", None)
    if log:
        return _event("thought", _agent_label(step), _truncate(str(log)), cls=cls)

    return _event("step", _agent_label(step), _truncate(str(step)), cls=cls)


def event_from_task(task_output: Any) -> dict[str, Any]:
    raw = getattr(task_output, "raw", None) or str(task_output)
    description = getattr(task_output, "description", "") or ""
    name = getattr(task_output, "name", "") or ""
    headline = name or description
    text = f"task complete · {_truncate(headline, 120)}"
    if raw:
        text += f"\n\n{_truncate(str(raw), 600)}"
    return _event("task_done", _agent_label(task_output), text, cls=type(task_output).__name__)


def _event(kind: str, agent: str, text: str, *, cls: str = "") -> dict[str, Any]:
    return {
        "ts": _now_iso(),
        "kind": kind,
        "agent": agent or "—",
        "text": text,
        "cls": cls,
    }


def append_event(events: list[dict[str, Any]], event: dict[str, Any]) -> list[dict[str, Any]]:
    """Append with a hard cap so the JSONL job record stays bounded."""
    events.append(event)
    if len(events) > EVENT_LIST_CAP:
        del events[: len(events) - EVENT_LIST_CAP]
    return events


def stage_event(agent: str, text: str) -> dict[str, Any]:
    """Synthetic high-level marker, e.g. handing off to the Visual Director."""
    return _event("stage", agent, _truncate(text, 200), cls="Stage")


# ---------------------------------------------------------------------------
# EventBus formatters — fine-grained signals from crewai_event_bus.
# Each takes the (source, event) signature crewAI dispatches with; `source`
# is unused but kept so handlers can be passed straight to the bus.
# ---------------------------------------------------------------------------

def event_from_tool_started(event: Any) -> dict[str, Any]:
    """ToolUsageStartedEvent → 🛠 entry. Always shows the tool name; args inline if compact."""
    tool = getattr(event, "tool_name", "") or "tool"
    args = getattr(event, "tool_args", None)
    text = f"calling `{tool}`"
    if args:
        text += f" · args: {_truncate(_format_args(args), 220)}"
    return _event("tool_started", _agent_label(event), text, cls=type(event).__name__)


def event_from_tool_finished(event: Any) -> dict[str, Any]:
    """ToolUsageFinishedEvent → 📥 entry with truncated output and duration if available."""
    tool = getattr(event, "tool_name", "") or "tool"
    output = getattr(event, "output", None)
    text = f"`{tool}` returned"
    duration = _duration_seconds(event)
    if duration is not None:
        text += f" in {duration:.1f}s"
    if getattr(event, "from_cache", False):
        text += " (cached)"
    if output is not None:
        text += f"\n\n{_truncate(str(output), 600)}"
    return _event("tool_result", _agent_label(event), text, cls=type(event).__name__)


def event_from_agent_started(event: Any) -> dict[str, Any]:
    """AgentExecutionStartedEvent → 👤 marker; useful when handoffs happen."""
    role = _agent_label(event)
    task = getattr(event, "task", None)
    task_label = ""
    if task is not None:
        task_label = (
            getattr(task, "name", "")
            or getattr(task, "description", "")
            or ""
        )
    text = "starting"
    if task_label:
        text += f" task: {_truncate(str(task_label), 200)}"
    return _event("agent_started", role, text, cls=type(event).__name__)


def event_from_reasoning_completed(event: Any) -> dict[str, Any]:
    """AgentReasoningCompletedEvent → 🧠 with the agent's plan text."""
    plan = getattr(event, "plan", "") or ""
    return _event("reasoning", _agent_label(event), _truncate(plan, 700), cls=type(event).__name__)


def _format_args(args: Any) -> str:
    """Tool args are sometimes a dict, sometimes a JSON string. Render as one line."""
    if isinstance(args, dict):
        try:
            import json as _json
            return _json.dumps(args, ensure_ascii=False, default=str)
        except Exception:
            return str(args)
    return str(args)


def _duration_seconds(event: Any) -> float | None:
    started = getattr(event, "started_at", None)
    finished = getattr(event, "finished_at", None)
    if started is None or finished is None:
        return None
    try:
        return (finished - started).total_seconds()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Emitter factory — bundles the (events list, lock, flush callback) into a
# set of bus-ready handlers. Caller registers them with crewai_event_bus.on()
# (or via scoped_handlers()).
# ---------------------------------------------------------------------------

class EventEmitter:
    """Thread-safe event emitter shared between worker thread and bus handlers."""

    def __init__(self, events: list[dict[str, Any]], flush: Callable[[], None]) -> None:
        self._events = events
        self._flush = flush
        self._lock = threading.Lock()

    def emit(self, event: dict[str, Any]) -> None:
        with self._lock:
            append_event(self._events, event)
        # Flush outside the lock so a slow store write doesn't block more handlers.
        try:
            self._flush()
        except Exception:
            pass

    # Bus handlers — bound methods, ready to register on crewai_event_bus.
    def on_tool_started(self, _source: Any, event: Any) -> None:
        self.emit(event_from_tool_started(event))

    def on_tool_finished(self, _source: Any, event: Any) -> None:
        self.emit(event_from_tool_finished(event))

    def on_agent_started(self, _source: Any, event: Any) -> None:
        self.emit(event_from_agent_started(event))

    def on_reasoning_completed(self, _source: Any, event: Any) -> None:
        self.emit(event_from_reasoning_completed(event))
