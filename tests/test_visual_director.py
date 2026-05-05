from backend.post_generator.visual_director import (
    _fallback_plan,
    _parse_json_block,
    extract_emotional_beats,
)


def test_extract_beats_dash_prefixed():
    fact_sheet = (
        "## Key Findings\n"
        "- thing 1\n\n"
        "## Emotional Beats\n"
        "- quiet relief\n"
        "- delayed buyer's remorse\n"
        "- vindicated skepticism\n\n"
        "## Sources\n"
    )
    beats = extract_emotional_beats(fact_sheet)
    assert beats == ["quiet relief", "delayed buyer's remorse", "vindicated skepticism"]


def test_extract_beats_caps_at_three():
    fact_sheet = "## Emotional Beats\n- a\n- b\n- c\n- d\n- e"
    assert extract_emotional_beats(fact_sheet) == ["a", "b", "c"]


def test_extract_beats_missing_section_returns_empty():
    assert extract_emotional_beats("no headings at all") == []


def test_parse_json_block_plain():
    assert _parse_json_block('{"a": 1}') == {"a": 1}


def test_parse_json_block_inside_fences():
    raw = "```json\n{\"a\": 1, \"b\": 2}\n```"
    assert _parse_json_block(raw) == {"a": 1, "b": 2}


def test_parse_json_block_inside_prose():
    raw = "Sure! Here's the plan:\n{\"x\": \"y\"}\nLet me know if you'd like changes."
    assert _parse_json_block(raw) == {"x": "y"}


def test_parse_json_block_invalid_returns_none():
    assert _parse_json_block("not json at all") is None


def test_fallback_plan_engineering_audience_has_keyboard_or_monitor():
    plan = _fallback_plan(post_text="anything", audience="engineering")
    scene = plan["scene"].lower()
    assert "monitor" in scene or "keyboard" in scene
    assert plan["model"] == "gpt-image-1"
    assert plan["image_prompt"]


def test_fallback_plan_business_audience_has_boardroom():
    plan = _fallback_plan(post_text="anything", audience="business")
    assert "boardroom" in plan["scene"].lower() or "founder" in plan["scene"].lower()
