"""
LinkedIn Post Generator — Streamlit Cockpit
Run with: uv run streamlit run app.py
"""

import os
import re
import sys
from datetime import date, datetime, timedelta
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
MODULE_OPTIONS = {
    "Community Sentiment": "community_sentiment",
    "Technical Deep Dive": "technical_deep_dive",
    "Tooling & Tactics": "tooling_and_tactics",
    "Long-form Strategy": "long_form_strategy",
    "Expert Synthesis": "expert_synthesis",
}

defaults = {
    "pulse_md": "",
    "pulse_done": False,
    "pulse_selected_modules": list(MODULE_OPTIONS.keys()),
    "pulse_days": 7,
    "imported_topic": "",
    "post_draft": "",
    "dalle_prompt": "",
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
            sections["__intro__"] = part.strip()
    return sections


def extract_finalized_post(raw: str) -> tuple[str, str]:
    """Parse critic output into (post_text, dalle_prompt)."""
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


def _convert_to_days(value: int, unit: str) -> int:
    return value * {"days": 1, "weeks": 7, "months": 30, "years": 365}[unit]


def check_readability(text: str) -> list[str]:
    """Return sentences with more than 15 words — flagged as too dense for LinkedIn."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s for s in sentences if s and len(s.split()) > 15]


def _generate_dalle_image(prompt: str) -> str:
    """Call DALL-E 3 directly and return the local saved file path."""
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        quality="standard",
        n=1,
    )
    image_url = resp.data[0].url
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("outputs") / "posts" / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{ts}.png"
    path.write_bytes(httpx.get(image_url, timeout=30.0).content)
    return str(path)


# ---------------------------------------------------------------------------
# Sidebar — runs on every full page rerun (not inside fragments)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Control Panel")

    # Scout synthesis backend
    from linkedin_post_generator.engines.pulse_scout import PulseScout as _PulseScout
    _scout_meta = _PulseScout()
    _use_openai_synth = _scout_meta._use_openai
    _backend_label = _scout_meta.synthesis_backend_label()

    st.subheader("Scout Synthesis Backend")
    if _use_openai_synth:
        st.success(f"☁️ {_backend_label}")
    else:
        ollama_ok_sidebar = check_ollama()
        if ollama_ok_sidebar:
            st.success(f"🖥️ {_backend_label} — Online ✓")
        else:
            st.error(f"🖥️ {_backend_label} — Offline")
            st.caption("Start with: `ollama serve`  OR set `SCOUT_USE_OPENAI=true`")

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
        for key in ["pulse_done", "crew_done", "post_draft", "dalle_prompt",
                    "image_path", "crew_raw_output", "imported_topic", "pulse_md"]:
            st.session_state[key] = False if isinstance(st.session_state[key], bool) else ""
        st.session_state.pulse_selected_modules = list(MODULE_OPTIONS.keys())
        st.session_state.pulse_days = 7
        st.session_state.cost_tracker = CostTracker()
        st.rerun()

    st.divider()
    st.caption(
        "**Engines:**\n\n"
        f"🛰️ Pulse Scout — {_backend_label} + 5 modules\n\n"
        "🏗️ Authority Crew — GPT-4o + Claude + DALL-E"
    )

# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------
st.title("🛰️ LinkedIn Post Generator")
st.caption("Dual-engine AI system — run Scout and Production Studio independently or simultaneously")

# ===========================================================================
# FRAGMENT 1 — Intelligence Feed (Pulse Scout)
# ===========================================================================
@st.fragment
def scout_section():
    st.header("1 · Intelligence Feed", divider="gray")

    from linkedin_post_generator.engines.pulse_scout import PulseScout

    scout = PulseScout()
    use_openai = scout._use_openai
    ollama_ok = use_openai or check_ollama()

    # --- Module & time range configuration ---
    selected_labels = st.multiselect(
        "Research Modules",
        options=list(MODULE_OPTIONS.keys()),
        default=st.session_state.pulse_selected_modules,
        help="Select one or more modules to research",
        disabled=st.session_state.pulse_done,
    )
    selected_modules = [MODULE_OPTIONS[l] for l in selected_labels]

    col_val, col_unit, col_info = st.columns([1, 2, 3])
    time_value = col_val.number_input(
        "Time window", min_value=1, max_value=730,
        value=st.session_state.pulse_days,
        disabled=st.session_state.pulse_done,
    )
    time_unit = col_unit.selectbox(
        "Unit", ["days", "weeks", "months", "years"],
        disabled=st.session_state.pulse_done,
    )
    days = _convert_to_days(int(time_value), time_unit)
    col_info.caption(f"Scanning the last **{days} days** across **{len(selected_modules)}** module(s)")

    # --- Run button row ---
    col_run, col_status = st.columns([2, 3])

    with col_run:
        scout_disabled = st.session_state.pulse_done or not ollama_ok or not selected_modules
        if st.button(
            "▶ Run Pulse Scout",
            disabled=scout_disabled,
            use_container_width=True,
            type="primary",
        ):
            st.session_state.pulse_selected_modules = selected_labels
            st.session_state.pulse_days = int(time_value)

            progress_bar = st.progress(0, text="Initialising...")

            synth_label = scout.synthesis_backend_label()
            _labels: dict[int, str] = {i: f"Scanning {selected_labels[i]}..." for i in range(len(selected_labels))}
            _labels[len(selected_labels)] = f"Synthesising with {synth_label}..."
            _labels[len(selected_labels) + 1] = "Complete!"

            def _progress_cb(step: int, total: int):
                pct = step / total
                progress_bar.progress(pct, text=_labels.get(step, f"Step {step}/{total}"))

            try:
                report = scout.run(
                    modules=selected_modules,
                    days=days,
                    progress_callback=_progress_cb,
                )
                st.session_state.pulse_md = report
                st.session_state.pulse_done = True
                progress_bar.empty()
                st.rerun()
            except Exception as e:
                progress_bar.empty()
                st.error(f"Pulse Scout failed: {e}")

        if not selected_modules and not st.session_state.pulse_done:
            st.warning("Select at least one module to run Pulse Scout.")

    with col_status:
        if st.session_state.pulse_done:
            st.success("Pulse report ready — import a topic below")
        elif not ollama_ok:
            st.warning("Ollama offline — set `SCOUT_USE_OPENAI=true` or run `ollama serve`")
        else:
            st.info("Configure modules and time range, then run Pulse Scout")

    # --- Display pulse report ---
    if st.session_state.pulse_md:
        sections = parse_h2_sections(st.session_state.pulse_md)

        for heading, body in sections.items():
            if heading == "__intro__":
                st.markdown(body)
                continue

            with st.expander(f"📌 {heading}", expanded=True):
                st.markdown(body)
                if st.button(
                    "Import → Production Studio",
                    key=f"import_{heading}",
                    help="Copy this topic to the Production Studio",
                ):
                    first_line = body.strip().splitlines()[0].lstrip("#- ").strip()
                    st.session_state.imported_topic = first_line[:120]
                    st.session_state.crew_done = False
                    st.toast(f"Topic imported: {first_line[:60]}... — scroll down to Production Studio", icon="✅")
                    # No st.rerun() here — production fragment picks up imported_topic on next interaction

        if st.button("↺ Re-run Pulse Scout", help="Clears the lock and runs a fresh scan"):
            st.session_state.pulse_done = False
            st.session_state.pulse_md = ""
            st.rerun()


# ===========================================================================
# FRAGMENT 2 — Production Studio + Final Output + Image Studio
# ===========================================================================
@st.fragment
def production_section():
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
            "Your Take (The Human Bridge)",
            placeholder=(
                "What do YOU actually think? This becomes the soul of the post.\n"
                "e.g. 'MoE is overhyped for inference cost — routing overhead kills "
                "the savings at small batch sizes'"
            ),
            height=100,
            help="Required for a human-sounding post. Your opinion separates a great post from an AI summary.",
        )
        author_vibe = st.text_area(
            "Mood / Tone for this post",
            placeholder=(
                "e.g. 'Skeptical — I think this is overhyped'\n"
                "'Excited but cautious — I've seen v1 fail before'\n"
                "'Direct and contrarian — push back on the consensus'"
            ),
            height=80,
            help="Seeds the writer agent's tone. Leave blank for default: calm, direct, slightly skeptical.",
        )

    with col_right:
        st.markdown("**Author Profile**")
        author_name = st.text_input("Name", value=profile["name"])
        author_title = st.text_input("Title", value=profile["title"])
        author_location = st.text_input("Location", value=profile["location"])

    st.divider()

    today = date.today()
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
                "author_vibe": author_vibe.strip() or "calm, direct, and slightly skeptical",
                "current_year": str(today.year),
                "current_date": today.strftime("%B %d, %Y"),
                "current_date_minus_90": (today - timedelta(days=90)).strftime("%B %d, %Y"),
            }

            with st.spinner("Authority Crew working... (this takes 2-4 minutes)"):
                try:
                    from linkedin_post_generator.engines.authority_crew.crew import AuthorityCrew

                    result = AuthorityCrew().crew().kickoff(inputs=inputs)
                    raw_output = str(result)
                    st.session_state.crew_raw_output = raw_output

                    post_draft, dalle_prompt = extract_finalized_post(raw_output)
                    st.session_state.post_draft = post_draft
                    st.session_state.dalle_prompt = dalle_prompt

                    st.session_state.cost_tracker.add_text(
                        input_text=str(inputs),
                        output_text=raw_output,
                    )

                    st.session_state.crew_done = True
                    st.rerun()

                except Exception as e:
                    st.error(f"Production Crew failed: {e}")
                    st.exception(e)

    if st.session_state.crew_done:
        st.success("Production complete — review and edit your post below")

    # --- Section 3: Final Output ---
    if st.session_state.post_draft:
        st.header("3 · Final Output", divider="gray")

        col_post, col_actions = st.columns([3, 1])

        with col_post:
            st.subheader("Post Draft")

            # Body char count (strip trailing hashtags)
            _body = re.split(r"\n+#", st.session_state.post_draft)[0].strip()
            char_count = len(_body)
            char_ok = char_count <= 1000
            st.caption(
                f"Body: {char_count} chars {'✓ under 1000' if char_ok else '⚠️ over 1000 — needs trimming'} "
                f"| Total: {len(st.session_state.post_draft)} chars"
            )

            edited_post = st.text_area(
                "Edit before publishing",
                value=st.session_state.post_draft,
                height=380,
                label_visibility="collapsed",
            )

            # Readability check
            dense = check_readability(edited_post)
            if dense:
                with st.expander(f"⚠️ Readability — {len(dense)} dense sentence(s) (>15 words)", expanded=False):
                    for s in dense:
                        st.warning(s)
            else:
                st.caption("✓ Readability passed — all sentences under 15 words")

        with col_actions:
            st.subheader("Export")
            if st.button("💾 Finalize & Export", type="primary", use_container_width=True):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                out_dir = Path("outputs") / "posts" / ts
                out_dir.mkdir(parents=True, exist_ok=True)
                final_path = out_dir / "post_final.md"
                final_path.write_text(edited_post)
                if st.session_state.image_path and Path(st.session_state.image_path).exists():
                    import shutil
                    img_src = Path(st.session_state.image_path)
                    shutil.copy(img_src, out_dir / img_src.name)
                st.success(f"Saved to `{final_path}`")

            st.download_button(
                label="⬇ Download Post (.md)",
                data=edited_post,
                file_name="linkedin_post.md",
                mime="text/markdown",
                use_container_width=True,
            )

            if st.button("↺ New Post", use_container_width=True):
                st.session_state.crew_done = False
                st.session_state.post_draft = ""
                st.session_state.dalle_prompt = ""
                st.session_state.image_path = ""
                st.session_state.crew_raw_output = ""
                st.rerun()

        # --- Image Studio ---
        st.divider()
        st.subheader("🎨 Image Studio")
        st.caption("Edit the AI-suggested prompt or write your own, then generate. Regenerate as many times as you like.")

        img_prompt = st.text_area(
            "Image Prompt",
            value=st.session_state.dalle_prompt,
            height=160,
            help="The crew suggested this prompt based on your post. Edit freely or replace entirely with custom instructions.",
            placeholder="Describe the visual you want. The AI has pre-filled a suggestion above.",
        )

        col_gen, col_img_info = st.columns([1, 3])
        generate_clicked = col_gen.button("🖼 Generate Image", type="primary", use_container_width=True)
        if not img_prompt.strip():
            col_img_info.caption("Enter a prompt above to generate an image.")

        if generate_clicked:
            if not img_prompt.strip():
                st.warning("Please enter an image prompt first.")
            else:
                with st.spinner("Generating image with DALL-E 3..."):
                    try:
                        path = _generate_dalle_image(img_prompt.strip())
                        st.session_state.image_path = path
                        st.session_state.dalle_prompt = img_prompt.strip()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Image generation failed: {e}")

        if st.session_state.image_path and Path(st.session_state.image_path).exists():
            st.image(st.session_state.image_path, use_container_width=True)
            st.download_button(
                "⬇ Download Image",
                data=Path(st.session_state.image_path).read_bytes(),
                file_name="post_image.png",
                mime="image/png",
            )


# ---------------------------------------------------------------------------
# Render fragments
# ---------------------------------------------------------------------------
scout_section()
production_section()
