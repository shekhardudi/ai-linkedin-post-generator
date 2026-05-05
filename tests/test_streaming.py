from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from backend.post_generator.streaming import (
    EVENT_LIST_CAP,
    EventEmitter,
    append_event,
    event_from_agent_started,
    event_from_reasoning_completed,
    event_from_step,
    event_from_task,
    event_from_tool_finished,
    event_from_tool_started,
    stage_event,
)


def _required_fields(evt):
    for f in ("ts", "kind", "agent", "text", "cls"):
        assert f in evt, f"missing {f}: {evt}"


def test_event_from_step_with_tool_call():
    step = SimpleNamespace(tool="arxiv_paper_search", tool_input={"query": "MoE"}, role="Researcher")
    evt = event_from_step(step)
    _required_fields(evt)
    assert evt["kind"] == "tool"
    assert "arxiv_paper_search" in evt["text"]
    assert evt["agent"] == "Researcher"


def test_event_from_step_with_log_text():
    step = SimpleNamespace(log="Thinking about the trade-offs of MoE…", role="Writer")
    evt = event_from_step(step)
    assert evt["kind"] == "thought"
    assert "MoE" in evt["text"]


def test_event_from_step_with_agent_finish():
    step = SimpleNamespace(return_values={"output": "All done."}, role="Critic")
    evt = event_from_step(step)
    assert evt["kind"] == "answer"
    assert evt["text"] == "All done."


def test_event_from_step_unknown_falls_back_to_str():
    step = SimpleNamespace()
    evt = event_from_step(step)
    assert evt["kind"] == "step"
    _required_fields(evt)


def test_event_from_task_includes_raw_excerpt():
    task = SimpleNamespace(raw="Body of the finalized post.", description="critique_task", role="Critic")
    evt = event_from_task(task)
    assert evt["kind"] == "task_done"
    assert "Body of the finalized post" in evt["text"]


def test_stage_event_marker():
    evt = stage_event("Visual Director", "Building image plan…")
    assert evt["kind"] == "stage"
    assert "image plan" in evt["text"]


def test_append_event_caps_list():
    events: list[dict] = []
    for i in range(EVENT_LIST_CAP + 30):
        append_event(events, {"ts": "x", "kind": "step", "agent": "a", "text": str(i), "cls": ""})
    assert len(events) == EVENT_LIST_CAP
    # Oldest entries dropped — should start at index >= 30
    assert int(events[0]["text"]) >= 30
    assert int(events[-1]["text"]) == EVENT_LIST_CAP + 29


# ---------------------------------------------------------------------------
# EventBus formatters
# ---------------------------------------------------------------------------

class _FakeToolStarted:
    def __init__(self, tool_name, tool_args, agent_role):
        self.tool_name = tool_name
        self.tool_args = tool_args
        self.agent_role = agent_role


class _FakeToolFinished:
    def __init__(self, tool_name, output, agent_role, duration_s=2.5, from_cache=False):
        self.tool_name = tool_name
        self.output = output
        self.agent_role = agent_role
        self.from_cache = from_cache
        self.started_at = datetime.now(timezone.utc)
        self.finished_at = self.started_at + timedelta(seconds=duration_s)


def test_event_from_tool_started_with_dict_args():
    e = _FakeToolStarted("tavily_search", {"query": "Mixture of Experts"}, "Researcher")
    evt = event_from_tool_started(e)
    _required_fields(evt)
    assert evt["kind"] == "tool_started"
    assert evt["agent"] == "Researcher"
    assert "tavily_search" in evt["text"]
    assert "Mixture of Experts" in evt["text"]


def test_event_from_tool_started_with_string_args():
    e = _FakeToolStarted("arxiv_paper_search", '{"query": "MoE routing"}', "Researcher")
    evt = event_from_tool_started(e)
    assert "arxiv_paper_search" in evt["text"]
    assert "MoE routing" in evt["text"]


def test_event_from_tool_started_with_no_args():
    e = _FakeToolStarted("internal_tool", None, "Writer")
    evt = event_from_tool_started(e)
    assert "internal_tool" in evt["text"]
    assert "args" not in evt["text"]


def test_event_from_tool_finished_includes_duration_and_output():
    e = _FakeToolFinished("tavily_search", "5 results returned…", "Researcher", duration_s=3.2)
    evt = event_from_tool_finished(e)
    assert evt["kind"] == "tool_result"
    assert "tavily_search" in evt["text"]
    assert "3.2s" in evt["text"]
    assert "5 results" in evt["text"]


def test_event_from_tool_finished_marks_cache_hits():
    e = _FakeToolFinished("tavily_search", "x", "Researcher", from_cache=True)
    evt = event_from_tool_finished(e)
    assert "(cached)" in evt["text"]


def test_event_from_agent_started_uses_agent_role():
    agent = SimpleNamespace(role="Technical Friction Researcher")
    task = SimpleNamespace(name="research_task", description="research X")
    e = SimpleNamespace(agent=agent, task=task, task_prompt="prompt")
    evt = event_from_agent_started(e)
    assert evt["kind"] == "agent_started"
    assert evt["agent"] == "Technical Friction Researcher"
    assert "research_task" in evt["text"]


def test_event_from_reasoning_completed_carries_plan():
    e = SimpleNamespace(agent_role="Writer", plan="Step 1: hook. Step 2: brain. Step 3: soul.")
    evt = event_from_reasoning_completed(e)
    assert evt["kind"] == "reasoning"
    assert evt["agent"] == "Writer"
    assert "Step 1" in evt["text"]


# ---------------------------------------------------------------------------
# Emitter
# ---------------------------------------------------------------------------

def test_event_emitter_writes_and_flushes():
    events: list[dict] = []
    flushes = {"n": 0}

    def _flush():
        flushes["n"] += 1

    em = EventEmitter(events, _flush)
    e = _FakeToolStarted("tavily_search", {"q": "test"}, "Researcher")
    em.on_tool_started(None, e)
    assert len(events) == 1
    assert flushes["n"] == 1
    assert events[0]["kind"] == "tool_started"


def test_event_emitter_thread_safe_under_concurrent_appends():
    import threading

    events: list[dict] = []
    em = EventEmitter(events, lambda: None)
    e = _FakeToolStarted("t", {"q": "x"}, "R")

    def _push():
        for _ in range(50):
            em.on_tool_started(None, e)

    threads = [threading.Thread(target=_push) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 8 * 50 = 400 emits; cap is 120 so only the last 120 survive,
    # but no exceptions should have escaped.
    assert len(events) == EVENT_LIST_CAP
    assert all(evt["kind"] == "tool_started" for evt in events)
