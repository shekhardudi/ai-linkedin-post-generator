from backend.utils.post_parser import extract_finalized_post, parse_h2_sections


def test_extract_both_sections():
    raw = (
        "## Finalized Post\n"
        "I was wrong about MoE. Here's what I learned.\n\n"
        "#AI #LLM\n\n"
        "## DALL-E Prompt\n"
        "A documentary still of an engineer at a whiteboard."
    )
    post, prompt = extract_finalized_post(raw)
    assert "I was wrong about MoE" in post
    assert prompt.startswith("A documentary still")


def test_image_prompt_heading_alias():
    raw = "## Finalized Post\nBody.\n\n## Image Prompt\nScene description."
    post, prompt = extract_finalized_post(raw)
    assert post == "Body."
    assert prompt == "Scene description."


def test_missing_image_prompt_returns_empty():
    raw = "## Finalized Post\nBody only.\n\n#AI"
    post, prompt = extract_finalized_post(raw)
    assert "Body only" in post
    assert prompt == ""


def test_no_headings_returns_raw_as_post():
    raw = "Plain text with no headings."
    post, prompt = extract_finalized_post(raw)
    assert post == "Plain text with no headings."
    assert prompt == ""


def test_parse_h2_sections_basic():
    md = "## A\nbody a\n\n## B\nbody b"
    sections = parse_h2_sections(md)
    assert sections == {"A": "body a", "B": "body b"}


def test_parse_h2_sections_with_intro():
    md = "intro paragraph\n\n## Heading\nbody"
    sections = parse_h2_sections(md)
    assert sections["__intro__"].startswith("intro")
    assert sections["Heading"] == "body"
