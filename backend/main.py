#!/usr/bin/env python
"""CLI entry points for the LinkedIn Post Generator backend."""

import json
import subprocess
import sys
import warnings
from datetime import date, timedelta
from pathlib import Path

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

from backend.post_generator.crew import AuthorityCrew
from backend.utils.user_profile import load_user_profile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_inputs() -> dict:
    profile = load_user_profile()
    today = date.today()
    return {
        "topic": "Agentic AI workflows",
        "leader_angle": "Why most agentic systems are overengineered for the problems they solve",
        "author_name": profile["name"],
        "author_title": profile["title"],
        "author_location": profile["location"],
        "author_vibe": "calm, direct, and slightly skeptical",
        "current_year": str(today.year),
        "current_date": today.strftime("%B %d, %Y"),
        "current_date_minus_90": (today - timedelta(days=90)).strftime("%B %d, %Y"),
    }


def _project_root() -> Path:
    """Repo root — backend/main.py lives at <root>/backend/main.py."""
    return Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Crew — single-shot
# ---------------------------------------------------------------------------

def run():
    """Run the Authority Crew (CLI entry point)."""
    AuthorityCrew().crew().kickoff(inputs=_default_inputs())


def run_scout():
    """Run Pulse Scout — all 5 modules, last 7 days."""
    from backend.scout.engine import PulseScout

    scout = PulseScout()

    if not scout._use_openai and not scout.check_ollama_health():
        print("ERROR: Ollama is not reachable and SCOUT_USE_OPENAI is not set.")
        print("Start Ollama with: ollama serve  OR  export SCOUT_USE_OPENAI=true")
        sys.exit(1)

    all_modules = list(scout.MODULE_REGISTRY.keys())

    def _progress(step: int, total: int):
        if step == total:
            print(f"  [{step}/{total}] Synthesis complete!")
        elif step == total - 1:
            print(f"  [{step}/{total}] Synthesising...")
        elif step < len(all_modules):
            label = scout.MODULE_REGISTRY[all_modules[step]].MODULE_LABEL
            print(f"  [{step}/{total}] Scanning {label}...")

    print("Running Pulse Scout (all 5 modules, last 7 days)...")
    report = scout.run(modules=all_modules, days=7, progress_callback=_progress)
    print("\nPulse report written to outputs/pulse_report.md\n")
    print(report[:600] + "..." if len(report) > 600 else report)


# ---------------------------------------------------------------------------
# API + UI launchers
# ---------------------------------------------------------------------------

def run_api():
    """Launch the FastAPI backend on :8000."""
    import uvicorn

    uvicorn.run(
        "backend.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )


def run_app():
    """Launch the Streamlit UI (talks to the FastAPI backend over HTTP)."""
    ui_path = _project_root() / "ui" / "streamlit_app.py"
    subprocess.run(["streamlit", "run", str(ui_path)], check=True)


# ---------------------------------------------------------------------------
# CrewAI tooling helpers (training / replay / test / trigger)
# ---------------------------------------------------------------------------

def train():
    """Train the crew for a given number of iterations."""
    AuthorityCrew().crew().train(
        n_iterations=int(sys.argv[1]),
        filename=sys.argv[2],
        inputs=_default_inputs(),
    )


def replay():
    """Replay the crew execution from a specific task."""
    AuthorityCrew().crew().replay(task_id=sys.argv[1])


def test():
    """Test the crew execution and return results."""
    AuthorityCrew().crew().test(
        n_iterations=int(sys.argv[1]),
        eval_llm=sys.argv[2],
        inputs=_default_inputs(),
    )


def run_with_trigger():
    """Run the crew with a JSON trigger payload."""
    if len(sys.argv) < 2:
        raise SystemExit("No trigger payload provided. Pass JSON as argv[1].")

    try:
        trigger_payload = json.loads(sys.argv[1])
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON payload: {exc}")

    inputs = {
        **_default_inputs(),
        "crewai_trigger_payload": trigger_payload,
        "topic": trigger_payload.get("topic", ""),
        "leader_angle": trigger_payload.get("leader_angle", ""),
    }

    return AuthorityCrew().crew().kickoff(inputs=inputs)
