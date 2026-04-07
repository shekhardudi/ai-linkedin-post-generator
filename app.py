"""
LinkedIn Post Generator — Streamlit Cockpit
Run with: uv run streamlit run app.py
"""

import re
import sys
from pathlib import Path

import httpx
import streamlit as st

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="LinkedIn Post Generator",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Ensure src/ is on the path when run directly
# ---------------------------------------------------------------------------
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from linkedin_post_generator.utils.cost_tracker import CostTracker
from linkedin_post_generator.utils.user_profile import load_user_profile

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
defaults = {
    "pulse_md": "",
    "pulse_done": False,
    "imported_topic": "",
    "post_draft": "",
    "image_path": "",
    "crew_done": False,
    "cost_tracker": CostTracker(),
    "crew_raw_output": "",
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def check_ollama(base_url: str = "http://localhost:11434") -> bool:
    try:
        r = httpx.get(f"{base_url}/api/tags", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def parse_h2_sections(md: str) -> dict[str, str]:
    """Split markdown on ## headings → {heading: body}."""
    if not md:
        return {}
    parts = re.split(r"\n(?=## )", md)
    sections = {}
    for part in parts:
        lines = part.strip().splitlines()
        if not lines:
            continue
        heading_line = lines[0]
        if heading_line.startswith("## "):
            heading = heading_line[3:].strip()
            body = "\n".join(lines[1:]).strip()
            sections[heading] = body
        else:
            # Content before first ## heading (intro/header)
            sections["__intro__"] = part.strip()
    return sections


def extract_finalized_post(raw: str) -> tuple[str, str]:
    """
    Parse the critic's output into (post_text, dalle_prompt).
    Returns (full_raw, "") if sections not found.
    """
    post_match = re.search(
        r"##\s*Finalized Post\s*\n(.*?)(?=\n##\s*DALL-E Prompt|\Z)",
        raw,
        re.DOTALL | re.IGNORECASE,
    )
    dalle_match = re.search(
        r"##\s*DALL-E Prompt\s*\n(.*?)$",
        raw,
        re.DOTALL | re.IGNORECASE,
    )
    post = post_match.group(1).strip() if post_match else raw.strip()
    dalle_prompt = dalle_match.group(1).strip() if dalle_match else ""
    return post, dalle_prompt


def find_latest_image() -> str:
    """Scan outputs/posts/ for the most recently generated image."""
    posts_dir = Path("outputs") / "posts"
    if not posts_dir.exists():
        return ""
    images = sorted(posts_dir.glob("**/*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(images[0]) if images else ""


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Control Panel")

    # Ollama status
    st.subheader("Ollama Status")
    ollama_ok = check_ollama()
    if ollama_ok:
        st.success("Online ✓")
    else:
        st.error("Offline — Pulse Scout disabled")
        st.caption("Start with: `ollama serve`")

    st.divider()

    # Cost tracker
    st.subheader("Cost Tracker (GPT-4o)")
    cost = st.session_state.cost_tracker.get_summary()
    col1, col2 = st.columns(2)
    col1.metric("Input tokens", f"{cost['input_tokens']:,}")
    col2.metric("Output tokens", f"{cost['output_tokens']:,}")
    st.metric("Estimated cost", f"${cost['estimated_cost_usd']:.4f} USD")
    st.caption("Estimate based on GPT-4o pricing: $5/M in, $15/M out")

    st.divider()

    # Reset
    if st.button("🔄 Reset Session", use_container_width=True):
        for key in ["pulse_done", "crew_done", "post_draft", "image_path", "crew_raw_output", "imported_topic"]:
            st.session_state[key] = False if isinstance(st.session_state[key], bool) else ""
        st.session_state.cost_tracker = CostTracker()
        st.rerun()

    st.divider()
    st.caption("**Engines:**\n\n🛰️ Pulse Scout — Ollama + ArXiv + HN\n\n🏗️ Authority Crew — GPT-4o + Claude + DALL-E")

# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------
st.title("🛰️ LinkedIn Post Generator")
st.caption("Dual-engine AI system: local intelligence briefing → premium post production")

# ===========================================================================
# SECTION 1 — Intelligence Feed (Pulse Scout)
# ===========================================================================
st.header("1 · Intelligence Feed", divider="gray")
st.caption("Pulse Scout scans ArXiv, tech news, and Hacker News to surface market signals.")

col_run, col_status = st.columns([2, 3])

with col_run:
    scout_disabled = st.session_state.pulse_done or not ollama_ok
    if st.button(
        "▶ Run Pulse Scout",
        disabled=scout_disabled,
        use_container_width=True,
        type="primary",
    ):
        from linkedin_post_generator.engines.pulse_scout import PulseScout

        scout = PulseScout()
        progress_bar = st.progress(0, text="Initialising...")
        status_text = st.empty()

        def _progress_cb(step: int, total: int):
            pct = step / total
            labels = {
                0: "Starting scan...",
                1: "✓ ArXiv scanned — fetching tech news...",
                2: "✓ Tech news done — scanning Hacker News...",
                3: "✓ HN scanned — synthesising with Ollama...",
                4: "✓ Synthesis complete!",
            }
            progress_bar.progress(pct, text=labels.get(step, f"Step {step}/{total}"))

        try:
            report = scout.run(progress_callback=_progress_cb)
            st.session_state.pulse_md = report
            st.session_state.pulse_done = True
            progress_bar.empty()
            status_text.empty()
            st.rerun()
        except Exception as e:
            progress_bar.empty()
            st.error(f"Pulse Scout failed: {e}")

with col_status:
    if st.session_state.pulse_done:
        st.success("Pulse report ready — import a topic below")
    elif not ollama_ok:
        st.warning("Ollama must be running to use Pulse Scout")
    else:
        st.info("Run Pulse Scout to generate your daily intelligence briefing")

# Display pulse report
if st.session_state.pulse_md:
    sections = parse_h2_sections(st.session_state.pulse_md)

    for heading, body in sections.items():
        if heading == "__intro__":
            st.markdown(body)
            continue

        with st.expander(f"📌 {heading}", expanded=True):
            st.markdown(body)
            if st.button(
                f"Import → Production Studio",
                key=f"import_{heading}",
                help="Copy this topic to the Production Studio",
            ):
                # Extract first meaningful line as the topic
                first_line = body.strip().splitlines()[0].lstrip("#- ").strip()
                st.session_state.imported_topic = first_line[:120]
                st.session_state.crew_done = False  # allow re-run with new topic
                st.toast(f"Topic imported: {first_line[:60]}...", icon="✅")
                st.rerun()

    # Option to re-run
    if st.button("↺ Re-run Pulse Scout", help="Clears the lock and runs a fresh scan"):
        st.session_state.pulse_done = False
        st.session_state.pulse_md = ""
        st.rerun()

# ===========================================================================
# SECTION 2 — Production Studio (Authority Crew)
# ===========================================================================
st.header("2 · Production Studio", divider="gray")
st.caption("Authority Crew turns your topic into a verified, world-class LinkedIn post.")

profile = load_user_profile()

col_left, col_right = st.columns([3, 2])

with col_left:
    topic = st.text_input(
        "Core Topic",
        value=st.session_state.imported_topic,
        placeholder="e.g. Mixture of Experts in production LLMs",
        help="The subject of your post",
    )
    leader_angle = st.text_area(
        "Your Angle / Perspective",
        placeholder=(
            "What's your actual take? e.g. 'MoE is overhyped for inference cost "
            "— the routing overhead kills the savings at small batch sizes'"
        ),
        height=120,
        help="Tell the AI what YOU actually think. This becomes the contrarian angle.",
    )

with col_right:
    st.markdown("**Author Profile**")
    author_name = st.text_input("Name", value=profile["name"])
    author_title = st.text_input("Title", value=profile["title"])
    author_location = st.text_input("Location", value=profile["location"])

st.divider()

crew_disabled = st.session_state.crew_done or not topic.strip()
if st.button(
    "▶ Run Production Crew",
    disabled=crew_disabled,
    type="primary",
    use_container_width=False,
    help="Runs the 3-agent cascade: Researcher → Thought Leader → Critic",
):
    if not topic.strip():
        st.warning("Please enter a topic first.")
    else:
        inputs = {
            "topic": topic,
            "leader_angle": leader_angle or "Focus on the practical implications for practitioners",
            "author_name": author_name,
            "author_title": author_title,
            "author_location": author_location,
            "current_year": str(__import__("datetime").datetime.now().year),
        }

        with st.spinner("Authority Crew working... (this takes 2-4 minutes)"):
            try:
                from linkedin_post_generator.engines.authority_crew.crew import AuthorityCrew

                result = AuthorityCrew().crew().kickoff(inputs=inputs)
                raw_output = str(result)
                st.session_state.crew_raw_output = raw_output

                # Parse sections
                post_draft, dalle_prompt = extract_finalized_post(raw_output)
                st.session_state.post_draft = post_draft

                # Track estimated token usage (post-run estimate from output length)
                st.session_state.cost_tracker.add_text(
                    input_text=str(inputs),
                    output_text=raw_output,
                )

                # Find generated image
                image_path = find_latest_image()
                st.session_state.image_path = image_path

                st.session_state.crew_done = True
                st.rerun()

            except Exception as e:
                st.error(f"Production Crew failed: {e}")
                st.exception(e)

if st.session_state.crew_done:
    st.success("Production complete — review your post below")

# ===========================================================================
# SECTION 3 — Final Output
# ===========================================================================
if st.session_state.post_draft or st.session_state.image_path:
    st.header("3 · Final Output", divider="gray")

    col_post, col_img = st.columns([3, 2])

    with col_post:
        st.subheader("Post Draft")
        char_count = len(st.session_state.post_draft)
        st.caption(f"Character count: {char_count} {'✓' if 1200 <= char_count <= 1800 else '⚠️ aim for 1200-1800'}")

        edited_post = st.text_area(
            "Edit before publishing",
            value=st.session_state.post_draft,
            height=400,
            label_visibility="collapsed",
        )

    with col_img:
        st.subheader("Generated Visual")
        if st.session_state.image_path and Path(st.session_state.image_path).exists():
            st.image(st.session_state.image_path, use_container_width=True)
        else:
            st.info("Image will appear here after the crew generates it")
            if st.button("🔍 Check for image"):
                st.session_state.image_path = find_latest_image()
                st.rerun()

    st.divider()

    col_save, col_download, col_reset = st.columns([2, 2, 1])

    with col_save:
        if st.button("💾 Finalize & Export", type="primary", use_container_width=True):
            from datetime import datetime

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = Path("outputs") / "posts" / ts
            out_dir.mkdir(parents=True, exist_ok=True)
            final_path = out_dir / "post_final.md"
            final_path.write_text(edited_post)

            # Copy image if it exists
            if st.session_state.image_path and Path(st.session_state.image_path).exists():
                import shutil
                img_src = Path(st.session_state.image_path)
                shutil.copy(img_src, out_dir / img_src.name)

            st.success(f"Saved to `{final_path}`")

    with col_download:
        st.download_button(
            label="⬇ Download Post (.md)",
            data=edited_post,
            file_name="linkedin_post.md",
            mime="text/markdown",
            use_container_width=True,
        )

    with col_reset:
        if st.button("↺ New Post", use_container_width=True):
            st.session_state.crew_done = False
            st.session_state.post_draft = ""
            st.session_state.image_path = ""
            st.session_state.crew_raw_output = ""
            st.rerun()
