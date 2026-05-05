"""
Engine 1: Pulse Scout — Modular Local Intelligence
Runs entirely on Ollama (free/local) + Tavily + crawl4ai + HN Algolia + ArXiv.
No crewAI overhead — pure Python pipeline for maximum simplicity and speed.

Five configurable modules:
  community_sentiment  — Reddit, X/Twitter, TLDR AI, Hacker News
  technical_deep_dive  — ArXiv research papers
  tooling_and_tactics  — Ben's Bites, The Neuron, The Rundown AI
  long_form_strategy   — Latent Space, Import AI, MIT Algorithm
  expert_synthesis     — The Batch (Andrew Ng), HuggingFace weekly
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import httpx
from langchain_core.messages import HumanMessage

from .pulse_scout_modules.base import BaseScanner, ScanResult
from .pulse_scout_modules.community_sentiment import CommunitySentimentScanner
from .pulse_scout_modules.expert_synthesis import ExpertSynthesisScanner
from .pulse_scout_modules.long_form_strategy import LongFormStrategyScanner
from .pulse_scout_modules.technical_deep_dive import TechnicalDeepDiveScanner
from .pulse_scout_modules.tooling_and_tactics import ToolingAndTacticsScanner


class PulseScout:
    """
    Orchestrates 5 pluggable intelligence modules and synthesises results
    via either a local Ollama LLM or OpenAI GPT-4o-mini (configurable).

    Config (environment variables):
      SCOUT_USE_OPENAI=true    → use GPT-4o-mini for synthesis (no Ollama required)
      SCOUT_USE_OPENAI=false   → use local Ollama (default)
      SCOUT_OPENAI_MODEL       → override OpenAI model (default: gpt-4o-mini)
      OLLAMA_BASE_URL          → Ollama server URL (default: http://localhost:11434)
      OLLAMA_MODEL             → Ollama model name (default: llama3.1)
    """

    def __init__(self):
        self._ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self._ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1")
        self._tavily_key = os.environ.get("TAVILY_API_KEY", "")
        self._use_openai = os.getenv("SCOUT_USE_OPENAI", "false").lower() == "true"
        self._openai_model = os.getenv("SCOUT_OPENAI_MODEL", "gpt-4o-mini")

        self.MODULE_REGISTRY: dict[str, BaseScanner] = {
            "community_sentiment": CommunitySentimentScanner(self._tavily_key),
            "technical_deep_dive": TechnicalDeepDiveScanner(),
            "tooling_and_tactics": ToolingAndTacticsScanner(),
            "long_form_strategy": LongFormStrategyScanner(),
            "expert_synthesis": ExpertSynthesisScanner(self._tavily_key),
        }

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def synthesis_backend_label(self) -> str:
        """Human-readable label for the active synthesis backend (used in sidebar)."""
        if self._use_openai:
            return f"OpenAI ({self._openai_model})"
        return f"Ollama ({self._ollama_model})"

    def check_ollama_health(self) -> bool:
        """Ping Ollama server. Returns True if reachable."""
        try:
            r = httpx.get(f"{self._ollama_base_url}/api/tags", timeout=3.0)
            return r.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Synthesis via Ollama
    # ------------------------------------------------------------------

    def _format_items(self, result: ScanResult) -> str:
        """Format a ScanResult's items into a compact string for the synthesis prompt."""
        if not result.items:
            return "(no data)"

        lines = []
        for item in result.items:
            if result.module_id == "technical_deep_dive":
                line = f"- [{item.get('published', '')}] {item.get('title', '')} — {item.get('abstract', '')[:150]}..."
            else:
                title = item.get("title", "")
                content = item.get("content", "")[:200]
                url = item.get("url", "")
                line = f"- {title}: {content}" if title else f"- [{url}] {content}"
            lines.append(line)
        return "\n".join(lines)

    def synthesize(self, results: list[ScanResult], days: int) -> str:
        """Call local Ollama to synthesize a structured intelligence briefing."""
        active = [r for r in results if r.items]
        if not active:
            return "_No data collected from the selected modules._"

        # Build the raw data block — one section per active module
        data_sections = []
        for r in active:
            data_sections.append(f"### {r.module_label}:\n{self._format_items(r)}")
        raw_data = "\n\n".join(data_sections)

        module_list = ", ".join(r.module_label for r in active)
        prompt = f"""You are an elite AI market intelligence analyst. The data below was gathered over the last {days} days across {len(active)} research module(s): {module_list}.

Write a concise Market Intelligence Briefing in markdown. Use EXACTLY this structure:

{chr(10).join(f"## {r.module_label}" + chr(10) + "2-3 sharp, specific insights drawn from this module's data. Name sources, techniques, figures, and implications. No generic statements." for r in active)}

## Cross-Module Synthesis
What patterns or contradictions emerge across ALL the modules above? What is the single most important signal a LinkedIn AI thought leader should act on right now?

## The Contrarian Angle
What important story is being overlooked or mis-framed across these sources? Where is the whitespace? What should practitioners actually pay attention to instead?

---
RAW DATA:

{raw_data}
---

Write the briefing now. Be sharp, specific, and contrarian where warranted."""

        if self._use_openai:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(model=self._openai_model, temperature=0.7)
        else:
            from langchain_ollama import ChatOllama
            llm = ChatOllama(
                model=self._ollama_model,
                base_url=self._ollama_base_url,
                temperature=0.7,
                num_ctx=8192,
            )
        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content

    # ------------------------------------------------------------------
    # Main runner
    # ------------------------------------------------------------------

    def run(
        self,
        modules: list[str],
        days: int = 7,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> str:
        """
        Run the selected Pulse Scout modules and synthesise results.

        Args:
            modules:           List of module IDs to run (keys of MODULE_REGISTRY).
            days:              Time window in days (0 = no filter).
            progress_callback: Optional callable(step, total) for UI progress tracking.

        Returns:
            The markdown report string (also saved to outputs/pulse_report.md).
        """
        selected = [self.MODULE_REGISTRY[m] for m in modules if m in self.MODULE_REGISTRY]
        total_steps = len(selected) + 1  # scans + synthesis

        def _tick(step: int):
            if progress_callback:
                progress_callback(step, total_steps)

        _tick(0)
        scan_results: list[ScanResult] = []
        for i, scanner in enumerate(selected):
            try:
                result = scanner.scan(days=days)
            except Exception as e:
                result = ScanResult(
                    module_id=scanner.MODULE_ID,
                    module_label=scanner.MODULE_LABEL,
                    items=[],
                    error=str(e),
                )
            scan_results.append(result)
            _tick(i + 1)

        report_md = self.synthesize(scan_results, days=days)
        _tick(total_steps)

        # Prepend a header with timestamp and config summary
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        module_labels = ", ".join(s.MODULE_LABEL for s in selected)
        full_report = (
            f"# Market Intelligence Briefing\n"
            f"_Generated: {timestamp} · Modules: {module_labels} · Last {days} days_\n\n"
            f"{report_md}"
        )

        # Append any scanner errors as a footnote
        errors = [(r.module_label, r.error) for r in scan_results if r.error]
        if errors:
            error_lines = "\n".join(f"- **{label}**: {err}" for label, err in errors)
            full_report += f"\n\n---\n_Scanner warnings:_\n{error_lines}"

        output_path = Path("outputs") / "pulse_report.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(full_report)

        return full_report
