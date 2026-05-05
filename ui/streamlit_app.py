"""LinkedIn Post Generator — Streamlit UI (pure API client).

Runs separately from the FastAPI backend. Set API_URL to point at the API.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import httpx
import streamlit as st

# Make `ui.api_client` importable when launched via `streamlit run ui/streamlit_app.py`
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ui import api_client as api  # noqa: E402


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="LinkedIn Post Generator",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)


MODULE_OPTIONS = {
    "Community Sentiment": "community_sentiment",
    "Technical Deep Dive": "technical_deep_dive",
    "Tooling & Tactics": "tooling_and_tactics",
    "Long-form Strategy": "long_form_strategy",
    "Expert Synthesis": "expert_synthesis",
}


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
defaults = {
    # Scout
    "scout_job_id": "",
    "scout_status": "",
    "scout_report_md": "",
    # `scout_module_labels` is the source of truth — bound to the multiselect's
    # key. The widget owns it; do not write to it from outside the widget on
    # rerun, or selections will reset every time the fragment refreshes.
    "scout_module_labels": list(MODULE_OPTIONS.keys()),
    "scout_days": 7,
    # Production
    "imported_topic": "",
    "post_job_id": "",
    "post_status": "",
    "post_draft": "",
    "image_prompt": "",
    "post_run_id": "",
    "image_paths": [],
    "post_cost": None,           # last completed run's cost_breakdown dict
    "session_cost_total": 0.0,   # cumulative spend this session
    "post_started_at": 0.0,      # epoch when current run started, for elapsed display
    # UI
    "active_tab": "Generate",
}
for k, v in defaults.items():
    st.session_state.setdefault(k, v)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _terminal(status: str) -> bool:
    return status in ("completed", "failed", "cancelled")


def _api_health() -> dict | None:
    try:
        return api.health()
    except Exception:
        return None


def _convert_to_days(value: int, unit: str) -> int:
    return value * {"days": 1, "weeks": 7, "months": 30, "years": 365}[unit]


def _parse_h2_sections(md: str) -> dict[str, str]:
    if not md:
        return {}
    parts = re.split(r"\n(?=## )", md)
    out: dict[str, str] = {}
    for part in parts:
        lines = part.strip().splitlines()
        if not lines:
            continue
        head = lines[0]
        if head.startswith("## "):
            out[head[3:].strip()] = "\n".join(lines[1:]).strip()
        else:
            out["__intro__"] = part.strip()
    return out


def _check_readability(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s for s in sentences if s and len(s.split()) > 15]


_KIND_ICON = {
    "thought": "🧠",
    "tool": "🛠",
    "tool_started": "🛠",
    "tool_result": "📥",
    "answer": "💬",
    "task_done": "✅",
    "stage": "🚦",
    "step": "•",
    "agent_started": "👤",
    "reasoning": "🧩",
}


def _render_event_feed(events: list[dict], height: int = 360) -> None:
    """Render the agent-thinking stream in a fixed-height scrollable container.

    Newest first so the user always sees the latest activity without scrolling.
    """
    if not events:
        st.caption("Waiting for the first agent step…")
        return
    box = st.container(height=height, border=True)
    with box:
        for evt in reversed(events[-60:]):
            icon = _KIND_ICON.get(evt.get("kind", "step"), "•")
            agent = evt.get("agent") or "—"
            text = (evt.get("text") or "").strip()
            ts = (evt.get("ts") or "")[11:19]  # HH:MM:SS
            header = f"**{icon} {agent}** · _{ts}_"
            st.markdown(header)
            if text:
                st.markdown(f"> {text}")
            st.markdown("")  # spacer


def _render_cost(cost: dict | None, label: str = "Run cost") -> None:
    if not cost:
        return
    total = float(cost.get("total_cost_usd", 0.0))
    crew = float((cost.get("crew") or {}).get("cost_usd", 0.0))
    vd = float((cost.get("visual_director") or {}).get("cost_usd", 0.0))
    img = (cost.get("image") or {})
    img_cost = float(img.get("cost_usd", 0.0))
    img_calls = int(img.get("calls", 0))
    st.metric(label, f"${total:,.4f}")
    st.caption(
        f"Crew: ${crew:.4f} · Visual Director: ${vd:.4f} · "
        f"Images ({img_calls}): ${img_cost:.4f}"
    )


# ---------------------------------------------------------------------------
# Sidebar — runs on every rerun
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Control Panel")

    health = _api_health()
    st.subheader("API")
    if health is None:
        st.error(f"Offline at {api.API_URL}")
        st.caption("Start the backend with: `make api`")
    else:
        st.success(f"Online · {api.API_URL}")
        st.caption(f"Scout backend: {health.get('scout_backend')}")
        keys = health.get("keys_present", {})
        missing = [k for k, v in keys.items() if not v]
        if missing:
            st.warning("Missing keys: " + ", ".join(missing))

    st.divider()

    st.subheader("Cost (this session)")
    st.metric("Total spend", f"${st.session_state.session_cost_total:,.4f}")
    if st.session_state.post_cost:
        with st.expander("Last run breakdown", expanded=False):
            _render_cost(st.session_state.post_cost, label="Last run")

    st.divider()

    if st.button("🔄 Reset Session", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

    st.divider()
    st.caption(
        "🛰️ **Pulse Scout** — 5 research modules\n\n"
        "🏗️ **Authority Crew** — Researcher → Writer → Critic → Visual Director"
    )


# ---------------------------------------------------------------------------
# Title + tabs
# ---------------------------------------------------------------------------
st.title("🛰️ LinkedIn Post Generator")
st.caption("Dual-engine AI system — scout intelligence and produce a post + image")

tab_generate, tab_history = st.tabs(["✨ Generate", "📚 History"])


# ===========================================================================
# Generate tab — Pulse Scout + Production Studio
# ===========================================================================

with tab_generate:

    # ---------------- Scout fragment ------------------------------------
    @st.fragment
    def scout_section():
        st.header("1 · Intelligence Feed", divider="gray")

        is_running = bool(st.session_state.scout_job_id) and not _terminal(st.session_state.scout_status)

        labels = st.multiselect(
            "Research Modules",
            list(MODULE_OPTIONS.keys()),
            key="scout_module_labels",
            disabled=is_running,
            help="Pick one or more modules. Each one fans out to its own set of sources.",
        )

        col_v, col_u, col_info = st.columns([1, 2, 3])
        time_value = col_v.number_input("Time window", 1, 730, st.session_state.scout_days, disabled=is_running)
        time_unit = col_u.selectbox("Unit", ["days", "weeks", "months", "years"], disabled=is_running)
        days = _convert_to_days(int(time_value), time_unit)
        col_info.caption(f"Scanning **{days} days** across **{len(labels)}** module(s)")

        col_run, col_status = st.columns([2, 3])

        with col_run:
            disabled = is_running or not labels or health is None
            if st.button("▶ Run Pulse Scout", type="primary", disabled=disabled, use_container_width=True):
                st.session_state.scout_days = int(time_value)
                try:
                    resp = api.start_scout([MODULE_OPTIONS[l] for l in labels], days)
                    st.session_state.scout_job_id = resp["job_id"]
                    st.session_state.scout_status = resp["status"]
                    st.session_state.scout_report_md = ""
                    st.rerun(scope="fragment")
                except httpx.HTTPError as e:
                    st.error(f"Failed to start scout: {e}")
            if not labels and not is_running:
                st.caption("⚠️ Pick at least one module to enable Run.")

        with col_status:
            if is_running:
                st.info("Pulse Scout running…")
            elif st.session_state.scout_status == "completed":
                st.success("Pulse report ready — import a topic below")
            elif st.session_state.scout_status == "failed":
                st.error("Scout failed — see details below")

        # Live polling while a job is in flight
        if is_running:
            try:
                state = api.poll_scout(st.session_state.scout_job_id)
            except httpx.HTTPError as e:
                st.error(f"Poll error: {e}")
                return
            st.session_state.scout_status = state["status"]
            progress = state.get("progress") or {}
            step = int(progress.get("step", 0))
            total = max(int(progress.get("total", 1)), 1)
            st.progress(step / total, text=f"Step {step}/{total}")

            if state["status"] == "completed":
                st.session_state.scout_report_md = (state.get("result") or {}).get("report_md", "")
            elif state["status"] == "failed":
                st.error(state.get("error") or "Scout failed.")

            # Re-run the fragment in 2s while still running
            if not _terminal(state["status"]):
                import time as _t
                _t.sleep(2)
                st.rerun(scope="fragment")
            else:
                st.rerun(scope="fragment")
            return

        # Display result if any
        report = st.session_state.scout_report_md
        if report:
            sections = _parse_h2_sections(report)
            for heading, body in sections.items():
                if heading == "__intro__":
                    st.markdown(body)
                    continue
                with st.expander(f"📌 {heading}", expanded=True):
                    st.markdown(body)
                    if st.button("Import → Production Studio", key=f"import_{heading}"):
                        first = body.strip().splitlines()[0].lstrip("#- ").strip()
                        st.session_state.imported_topic = first[:120]
                        st.toast(f"Imported: {first[:60]}...", icon="✅")

            if st.button("↺ Re-run Pulse Scout", help="Clear and run again"):
                st.session_state.scout_job_id = ""
                st.session_state.scout_status = ""
                st.session_state.scout_report_md = ""
                st.rerun(scope="fragment")

    scout_section()


    # ---------------- Production fragment -------------------------------
    @st.fragment
    def production_section():
        st.header("2 · Production Studio", divider="gray")
        st.caption("Authority Crew turns your topic into a verified, world-class LinkedIn post.")

        is_running = bool(st.session_state.post_job_id) and not _terminal(st.session_state.post_status)
        is_done = st.session_state.post_status == "completed"

        col_left, col_right = st.columns([3, 2])

        with col_left:
            topic = st.text_input(
                "Core Topic",
                value=st.session_state.imported_topic,
                placeholder="e.g. Mixture of Experts in production LLMs",
                disabled=is_running,
            )
            leader_angle = st.text_area(
                "Your Take (The Human Bridge)",
                placeholder="The opinion that becomes the soul of the post.",
                height=100,
                disabled=is_running,
            )
            author_vibe = st.text_area(
                "Mood / Tone for this post",
                placeholder="e.g. 'Skeptical — I think this is overhyped'",
                height=80,
                disabled=is_running,
            )

        with col_right:
            st.markdown("**Author Profile**")
            author_name = st.text_input("Name", value="Shekhar Dudi", disabled=is_running)
            author_title = st.text_input("Title", value="AI Engineer", disabled=is_running)
            author_location = st.text_input("Location", value="Melbourne, Australia", disabled=is_running)
            audience = st.radio(
                "Audience",
                ["engineering", "business"],
                horizontal=True,
                disabled=is_running,
                help="Drives the visual style of the generated image.",
            )

        st.divider()

        if st.button(
            "▶ Run Production Crew",
            type="primary",
            disabled=is_running or is_done or not topic.strip() or health is None,
        ):
            try:
                resp = api.start_post({
                    "topic": topic,
                    "leader_angle": leader_angle or "Focus on the practical implications for practitioners",
                    "author_name": author_name,
                    "author_title": author_title,
                    "author_location": author_location,
                    "author_vibe": author_vibe.strip() or "calm, direct, and slightly skeptical",
                    "audience": audience,
                })
                import time as _t0
                st.session_state.post_job_id = resp["job_id"]
                st.session_state.post_status = resp["status"]
                st.session_state.post_draft = ""
                st.session_state.image_prompt = ""
                st.session_state.image_paths = []
                st.session_state.post_cost = None
                st.session_state.post_started_at = _t0.time()
                st.rerun(scope="fragment")
            except httpx.HTTPError as e:
                st.error(f"Failed to start crew: {e}")

        # Live polling
        if is_running:
            try:
                state = api.poll_post(st.session_state.post_job_id)
            except httpx.HTTPError as e:
                st.error(f"Poll error: {e}")
                return
            st.session_state.post_status = state["status"]
            progress = state.get("progress") or {}
            stage_name = progress.get("stage", "queued")
            events = progress.get("events") or []

            import time as _t
            elapsed = int(_t.time() - (st.session_state.post_started_at or _t.time()))

            stage_pretty = {
                "research": "📚 Researcher gathering facts",
                "writing": "✍️  Writer drafting the post",
                "critique": "🪤 Critic line-editing",
                "visual_director": "🎨 Visual Director planning the image",
                "queued": "Queued…",
            }.get(stage_name, stage_name)

            st.markdown(f"### {stage_pretty}  ·  ⏱ {elapsed//60:02d}:{elapsed%60:02d}")
            st.caption("Streaming agent activity — newest first.")
            _render_event_feed(events, height=380)

            if state["status"] == "completed":
                result = state.get("result") or {}
                st.session_state.post_draft = result.get("post_draft", "")
                st.session_state.image_prompt = result.get("image_prompt", "")
                st.session_state.post_run_id = result.get("run_id", "")
                cost = result.get("cost_breakdown") or {}
                st.session_state.post_cost = cost
                st.session_state.session_cost_total = round(
                    float(st.session_state.session_cost_total)
                    + float(cost.get("total_cost_usd", 0.0)),
                    6,
                )
            elif state["status"] == "failed":
                st.error(state.get("error") or "Crew failed.")

            if not _terminal(state["status"]):
                _t.sleep(3)
                st.rerun(scope="fragment")
            else:
                st.rerun(scope="fragment")
            return

        if is_done:
            st.success("Production complete — review and edit your post below")

        # ---------- Final Output + Image Studio ---------------------------
        if st.session_state.post_draft:
            st.header("3 · Final Output", divider="gray")

            col_post, col_actions = st.columns([3, 1])

            with col_post:
                st.subheader("Post Draft")
                body = re.split(r"\n+#", st.session_state.post_draft)[0].strip()
                char_count = len(body)
                ok = char_count <= 1000
                st.caption(
                    f"Body: {char_count} chars "
                    f"{'✓ under 1000' if ok else '⚠️ over 1000 — trim'} | "
                    f"Total: {len(st.session_state.post_draft)} chars"
                )
                edited = st.text_area(
                    "Edit before publishing",
                    value=st.session_state.post_draft,
                    height=380,
                    label_visibility="collapsed",
                )
                dense = _check_readability(edited)
                if dense:
                    with st.expander(f"⚠️ Readability — {len(dense)} dense sentence(s) (>15 words)"):
                        for s in dense:
                            st.warning(s)
                else:
                    st.caption("✓ All sentences under 15 words")

            with col_actions:
                st.subheader("Export")
                if st.button("💾 Save edits", type="primary", use_container_width=True):
                    try:
                        api.update_post(st.session_state.post_job_id, edited)
                        st.session_state.post_draft = edited
                        st.success("Saved to history")
                    except httpx.HTTPError as e:
                        st.error(f"Save failed: {e}")

                st.download_button(
                    "⬇ Download Post (.md)",
                    data=edited,
                    file_name="linkedin_post.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
                if st.button("↺ New Post", use_container_width=True):
                    for k in ("post_job_id", "post_status", "post_draft", "image_prompt",
                              "post_run_id", "image_paths"):
                        st.session_state[k] = "" if isinstance(st.session_state[k], str) else []
                    st.session_state.post_cost = None
                    st.rerun(scope="fragment")

                if st.session_state.post_cost:
                    st.divider()
                    _render_cost(st.session_state.post_cost, label="This run")

            # Image Studio
            st.divider()
            st.subheader("🎨 Image Studio")
            st.caption("Edit the AI-suggested prompt or replace it. Regenerate as many times as you like.")

            img_prompt = st.text_area(
                "Image Prompt",
                value=st.session_state.image_prompt,
                height=160,
                placeholder="The crew suggested a prompt. Edit freely.",
            )

            col_gen, col_qual, col_info = st.columns([1, 1, 2])
            generate_clicked = col_gen.button("🖼 Generate Image", type="primary", use_container_width=True)
            quality = col_qual.selectbox(
                "Quality",
                ["medium", "high", "low"],
                index=0,
                help="medium ≈ 30s · high ≈ 70s · low ≈ 12s. Medium is the LinkedIn sweet spot.",
            )
            if not img_prompt.strip():
                col_info.caption("Enter a prompt above to generate.")

            if generate_clicked:
                if not img_prompt.strip():
                    st.warning("Enter an image prompt first.")
                else:
                    with st.spinner(f"Generating image ({quality} quality)…"):
                        try:
                            resp = api.generate_image(
                                st.session_state.post_job_id,
                                img_prompt.strip(),
                                quality=quality,
                            )
                            # Refresh cost from server-side cumulative breakdown
                            try:
                                latest = api.poll_post(st.session_state.post_job_id)
                                latest_cost = (latest.get("result") or {}).get("cost_breakdown") or {}
                                if latest_cost:
                                    prev_total = float((st.session_state.post_cost or {}).get("total_cost_usd", 0.0))
                                    new_total = float(latest_cost.get("total_cost_usd", 0.0))
                                    delta = max(new_total - prev_total, 0.0)
                                    st.session_state.post_cost = latest_cost
                                    st.session_state.session_cost_total = round(
                                        float(st.session_state.session_cost_total) + delta, 6
                                    )
                            except Exception:
                                pass
                            st.session_state.image_prompt = img_prompt.strip()
                            st.session_state.image_paths = (
                                st.session_state.image_paths + [resp["image_id"]]
                            )
                            st.rerun(scope="fragment")
                        except httpx.HTTPError as e:
                            st.error(f"Image generation failed: {e}")

            # Show the most recent images (up to 4)
            if st.session_state.image_paths:
                cols = st.columns(min(len(st.session_state.image_paths), 4))
                for col, image_id in zip(cols, st.session_state.image_paths[-4:]):
                    with col:
                        try:
                            img = api.image_bytes(image_id)
                            st.image(img, use_container_width=True)
                            st.download_button(
                                "⬇ Download",
                                data=img,
                                file_name=f"{image_id}.png",
                                mime="image/png",
                                use_container_width=True,
                            )
                        except Exception as e:
                            st.error(f"Failed to load {image_id}: {e}")

    production_section()


# ===========================================================================
# History tab
# ===========================================================================

with tab_history:
    st.header("📚 Run History", divider="gray")
    try:
        rows = api.list_history(limit=100)
    except httpx.HTTPError as e:
        st.error(f"History unavailable: {e}")
        rows = []

    if not rows:
        st.info("No runs yet. Generate a post to see it here.")
    else:
        for row in rows:
            with st.expander(
                f"🗓 {row['created_at'][:19].replace('T', ' ')} · {row.get('topic', 'untitled')}",
                expanded=False,
            ):
                st.caption(f"Run ID: `{row['run_id']}`")
                if row.get("leader_angle"):
                    st.markdown(f"**Angle:** {row['leader_angle']}")
                if row.get("post_path"):
                    post_path = _REPO_ROOT / row["post_path"]
                    if post_path.exists():
                        st.text_area(
                            "Post",
                            value=post_path.read_text(encoding="utf-8"),
                            height=240,
                            key=f"hist_post_{row['run_id']}",
                            disabled=True,
                        )
                if row.get("image_paths"):
                    img_cols = st.columns(min(len(row["image_paths"]), 4))
                    for col, p in zip(img_cols, row["image_paths"][-4:]):
                        full = _REPO_ROOT / p
                        if full.exists():
                            with col:
                                st.image(str(full), use_container_width=True)
