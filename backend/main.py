#!/usr/bin/env python
import json
import subprocess
import sys
import warnings
from datetime import datetime, date, timedelta

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

from linkedin_post_generator.engines.authority_crew.crew import AuthorityCrew
from linkedin_post_generator.utils.user_profile import load_user_profile


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


def run():
    """Run the Authority Crew (CLI entry point)."""
    try:
        AuthorityCrew().crew().kickoff(inputs=_default_inputs())
    except Exception as e:
        raise Exception(f"An error occurred while running the crew: {e}")


def run_scout():
    """Run Pulse Scout engine (CLI entry point) — all 5 modules, last 7 days."""
    from linkedin_post_generator.engines.pulse_scout import PulseScout

    scout = PulseScout()

    if not scout.check_ollama_health():
        print("ERROR: Ollama is not reachable at the configured URL.")
        print("Start Ollama with: ollama serve")
        sys.exit(1)

    all_modules = list(scout.MODULE_REGISTRY.keys())

    def _progress(step: int, total: int):
        if step == total:
            print(f"  [{step}/{total}] Synthesis complete!")
        elif step == total - 1:
            print(f"  [{step}/{total}] Synthesising with Ollama...")
        elif step < len(all_modules):
            label = scout.MODULE_REGISTRY[all_modules[step]].MODULE_LABEL
            print(f"  [{step}/{total}] Scanning {label}...")

    print("Running Pulse Scout (all 5 modules, last 7 days)...")
    report = scout.run(modules=all_modules, days=7, progress_callback=_progress)
    print("\nPulse report written to outputs/pulse_report.md\n")
    print(report[:600] + "..." if len(report) > 600 else report)


def run_app():
    """Launch the Streamlit UI."""
    import os
    from pathlib import Path

    app_path = Path(__file__).parent.parent.parent.parent / "app.py"
    subprocess.run(["streamlit", "run", str(app_path)], check=True)


def train():
    """Train the crew for a given number of iterations."""
    try:
        AuthorityCrew().crew().train(
            n_iterations=int(sys.argv[1]),
            filename=sys.argv[2],
            inputs=_default_inputs(),
        )
    except Exception as e:
        raise Exception(f"An error occurred while training the crew: {e}")


def replay():
    """Replay the crew execution from a specific task."""
    try:
        AuthorityCrew().crew().replay(task_id=sys.argv[1])
    except Exception as e:
        raise Exception(f"An error occurred while replaying the crew: {e}")


def test():
    """Test the crew execution and return results."""
    try:
        AuthorityCrew().crew().test(
            n_iterations=int(sys.argv[1]),
            eval_llm=sys.argv[2],
            inputs=_default_inputs(),
        )
    except Exception as e:
        raise Exception(f"An error occurred while testing the crew: {e}")


def run_with_trigger():
    """Run the crew with a JSON trigger payload."""
    if len(sys.argv) < 2:
        raise Exception("No trigger payload provided. Please provide JSON payload as argument.")

    try:
        trigger_payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        raise Exception("Invalid JSON payload provided as argument")

    inputs = {
        **_default_inputs(),
        "crewai_trigger_payload": trigger_payload,
        "topic": trigger_payload.get("topic", ""),
        "leader_angle": trigger_payload.get("leader_angle", ""),
    }

    try:
        return AuthorityCrew().crew().kickoff(inputs=inputs)
    except Exception as e:
        raise Exception(f"An error occurred while running the crew with trigger: {e}")
