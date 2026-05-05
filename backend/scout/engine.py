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

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import httpx
from langchain_core.messages import HumanMessage

from backend.core.settings import get_settings

from .modules.base import BaseScanner, ScanResult
from .modules.community_sentiment import CommunitySentimentScanner
from .modules.expert_synthesis import ExpertSynthesisScanner
from .modules.long_form_strategy import LongFormStrategyScanner
from .modules.technical_deep_dive import TechnicalDeepDiveScanner
from .modules.tooling_and_tactics import ToolingAndTacticsScanner


class PulseScout:
    """Orchestrates 5 pluggable intelligence modules.

    Synthesis runs via either a local Ollama LLM or an OpenAI model. All
    settings (which backend, which model, temperature, ctx window) come from
    `backend.core.settings.Settings` — override via env vars or `.env`.
    """

    def __init__(self):
        s = get_settings()
        self._ollama_base_url = s.ollama_base_url
        self._ollama_model = s.ollama_model
        self._ollama_num_ctx = s.ollama_num_ctx
        self._tavily_key = s.tavily_api_key
        self._use_openai = s.scout_use_openai
        self._openai_model = s.scout_openai_model
        self._synthesis_temperature = s.scout_synthesis_temperature

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

    def synthesize(self, results: list[ScanResult], days: int) -> tuple[str, dict]:
        """Call local Ollama / OpenAI to synthesize a structured intelligence briefing.

        Returns (markdown, usage_meta) where usage_meta is
        ``{"model": str, "input_tokens": int, "output_tokens": int, "total_tokens": int}``
        when the provider reports usage; otherwise zeros.
        """
        active = [r for r in results if r.items]
        if not active:
            return "_No data collected from the selected modules._", {}

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
            llm = ChatOpenAI(model=self._openai_model, temperature=self._synthesis_temperature)
            model_name = f"openai/{self._openai_model}"
        else:
            from langchain_ollama import ChatOllama
            llm = ChatOllama(
                model=self._ollama_model,
                base_url=self._ollama_base_url,
                temperature=self._synthesis_temperature,
                num_ctx=self._ollama_num_ctx,
            )
            model_name = f"ollama/{self._ollama_model}"
        response = llm.invoke([HumanMessage(content=prompt)])

        usage = getattr(response, "usage_metadata", None) or {}
        meta = (getattr(response, "response_metadata", None) or {}).get("token_usage") or {}
        input_tokens = int(usage.get("input_tokens") or meta.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or meta.get("completion_tokens") or 0)
        usage_meta = {
            "model": model_name,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }
        return response.content, usage_meta

    # ------------------------------------------------------------------
    # Main runner
    # ------------------------------------------------------------------

    def run(
        self,
        modules: list[str],
        days: int = 7,
        progress_callback: Optional[Callable[[int, int, Optional[dict[str, Any]]], None]] = None,
    ) -> tuple[str, dict]:
        """
        Run the selected Pulse Scout modules and synthesise results.

        Args:
            modules:           List of module IDs to run (keys of MODULE_REGISTRY).
            days:              Time window in days (0 = no filter).
            progress_callback: Optional callable(step, total) for UI progress tracking.

        Returns:
            ``(markdown_report, cost_breakdown)`` where ``cost_breakdown`` matches
            the shape consumed by the frontend ``CostTracker`` component.
        """
        selected = [self.MODULE_REGISTRY[m] for m in modules if m in self.MODULE_REGISTRY]
        total_steps = len(selected) + 1  # scans + synthesis

        def _tick(step: int, meta: Optional[dict[str, Any]] = None):
            if progress_callback:
                progress_callback(step, total_steps, meta)

        _tick(0, {
            "module": selected[0].MODULE_ID if selected else "synthesis",
            "phase": "started",
            "message": "Scout run started.",
        })
        scan_results: list[ScanResult] = []
        for i, scanner in enumerate(selected):
            _tick(i, {
                "module": scanner.MODULE_ID,
                "phase": "started",
                "message": f"Running {scanner.MODULE_LABEL}…",
            })
            try:
                result = scanner.scan(days=days)
                phase = "done"
                message = f"Completed {scanner.MODULE_LABEL} ({len(result.items)} items)."
            except Exception as e:
                result = ScanResult(
                    module_id=scanner.MODULE_ID,
                    module_label=scanner.MODULE_LABEL,
                    items=[],
                    error=str(e),
                )
                phase = "error"
                message = f"{scanner.MODULE_LABEL} failed: {e}"
            scan_results.append(result)
            _tick(i + 1, {
                "module": scanner.MODULE_ID,
                "phase": phase,
                "message": message,
            })

        _tick(len(selected), {
            "module": "synthesis",
            "phase": "started",
            "message": "Synthesizing final briefing…",
        })

        report_md, usage_meta = self.synthesize(scan_results, days=days)
        _tick(total_steps, {
            "module": "synthesis",
            "phase": "done",
            "message": "Briefing generated.",
        })

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

        # Build cost_breakdown in the same shape the frontend already consumes.
        from backend.core.pricing import text_cost

        model = usage_meta.get("model", "")
        in_tok = int(usage_meta.get("input_tokens", 0))
        out_tok = int(usage_meta.get("output_tokens", 0))
        cost_usd = round(text_cost(model, in_tok, out_tok), 6) if model else 0.0
        cost_breakdown = {
            "scout": {
                "model": model,
                "prompt_tokens": in_tok,
                "completion_tokens": out_tok,
                "total_tokens": in_tok + out_tok,
                "cost_usd": cost_usd,
            },
            "total_cost_usd": cost_usd,
        }

        return full_report, cost_breakdown
