"""
Engine 1: Pulse Scout — Local Intelligence
Runs entirely on Ollama (free/local) + Tavily + HN Algolia API.
No crewAI overhead — pure Python pipeline for maximum simplicity and speed.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import arxiv
import httpx
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage
from tavily import TavilyClient


class PulseScout:
    """
    Scans 3 intelligence vectors and synthesizes a market briefing via local Ollama.

    Vector 1 — The Alpha:   ArXiv (technical breakthroughs)
    Vector 2 — The Hype:    Tech news via Tavily (M&A, products, policy)
    Vector 3 — The Gap:     Hacker News Algolia (developer sentiment & pain points)
    """

    TOTAL_STEPS = 4  # 3 scans + 1 synthesis

    def __init__(self):
        self._ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self._ollama_model = os.getenv("OLLAMA_MODEL", "llama3.1")
        self._tavily_key = os.environ.get("TAVILY_API_KEY", "")

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def check_ollama_health(self) -> bool:
        """Ping Ollama server. Returns True if reachable."""
        try:
            r = httpx.get(f"{self._ollama_base_url}/api/tags", timeout=3.0)
            return r.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Vector 1 — ArXiv (The Alpha)
    # ------------------------------------------------------------------

    def scan_vector_1_arxiv(self) -> list[dict]:
        """Fetch the latest AI/ML papers from ArXiv."""
        client = arxiv.Client()
        search = arxiv.Search(
            query="(artificial intelligence OR large language model OR LLM OR AI agent) AND (2024 OR 2025)",
            max_results=6,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )
        results = []
        for paper in client.results(search):
            results.append({
                "title": paper.title,
                "authors": [a.name for a in paper.authors[:3]],
                "abstract": paper.summary[:400].replace("\n", " "),
                "published": paper.published.strftime("%Y-%m-%d"),
                "url": paper.entry_id,
            })
        return results

    # ------------------------------------------------------------------
    # Vector 2 — Tech News (The Hype)
    # ------------------------------------------------------------------

    def scan_vector_2_tech_news(self) -> list[dict]:
        """Search for AI business/product/policy news via Tavily."""
        if not self._tavily_key:
            return [{"title": "Tavily API key not set", "content": "", "url": ""}]

        client = TavilyClient(api_key=self._tavily_key)
        response = client.search(
            query="AI machine learning company acquisitions products policy announcements 2025",
            search_depth="advanced",
            topic="news",
            max_results=6,
        )
        results = []
        for r in response.get("results", []):
            results.append({
                "title": r.get("title", ""),
                "content": r.get("content", "")[:300],
                "url": r.get("url", ""),
                "published": r.get("published_date", ""),
            })
        return results

    # ------------------------------------------------------------------
    # Vector 3 — Hacker News (The Gap)
    # ------------------------------------------------------------------

    def scan_vector_3_dev_community(self) -> list[dict]:
        """Fetch trending AI/ML stories from Hacker News (free, no key)."""
        try:
            response = httpx.get(
                "https://hn.algolia.com/api/v1/search_by_date",
                params={
                    "query": "AI LLM machine learning agent",
                    "tags": "story",
                    "hitsPerPage": 15,
                    "numericFilters": "points>30",
                },
                timeout=10.0,
            )
            response.raise_for_status()
            hits = response.json().get("hits", [])[:8]
            return [
                {
                    "title": h.get("title", ""),
                    "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                    "points": h.get("points", 0),
                    "comments": h.get("num_comments", 0),
                    "date": (h.get("created_at") or "")[:10],
                }
                for h in hits
            ]
        except Exception as e:
            return [{"title": f"HN fetch failed: {e}", "url": "", "points": 0, "comments": 0, "date": ""}]

    # ------------------------------------------------------------------
    # Synthesis via Ollama
    # ------------------------------------------------------------------

    def synthesize(
        self,
        v1_arxiv: list[dict],
        v2_news: list[dict],
        v3_hn: list[dict],
    ) -> str:
        """Call local Ollama to synthesize a structured intelligence briefing."""

        def fmt_arxiv(items):
            return "\n".join(
                f"- [{p['published']}] {p['title']} — {p['abstract'][:150]}..."
                for p in items
            )

        def fmt_news(items):
            return "\n".join(
                f"- {n['title']}: {n['content'][:150]}"
                for n in items
                if n.get("title")
            )

        def fmt_hn(items):
            return "\n".join(
                f"- [{i['points']}pts, {i['comments']} comments] {i['title']}"
                for i in items
                if i.get("title")
            )

        prompt = f"""You are an elite AI market intelligence analyst. Based on the raw data below, write a concise Market Intelligence Briefing in markdown.

STRUCTURE (use EXACTLY these H2 headings):

## Vector 1: The Alpha (Technical Shifts)
Identify the 2-3 most significant technical breakthroughs or research directions from the ArXiv papers. Be specific — name techniques, numbers, implications.

## Vector 2: The Hype (Marketing Shifts)
From the tech news, identify what narratives are being pushed by companies and media. What are they over-emphasizing? What is being spun?

## Vector 3: The Gap (Opportunity)
Cross-reference all three sources. What important problem or angle is NOT being addressed? Where is the whitespace? What should practitioners actually pay attention to?

---
RAW DATA:

### ArXiv Papers (last 7 days):
{fmt_arxiv(v1_arxiv)}

### Tech News:
{fmt_news(v2_news)}

### Hacker News (developer pulse):
{fmt_hn(v3_hn)}
---

Write the briefing now. Be sharp, contrarian where warranted, and specific. No generic statements."""

        llm = ChatOllama(
            model=self._ollama_model,
            base_url=self._ollama_base_url,
            temperature=0.7,
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content

    # ------------------------------------------------------------------
    # Main runner
    # ------------------------------------------------------------------

    def run(self, progress_callback: Optional[Callable[[int, int], None]] = None) -> str:
        """
        Run the full Pulse Scout pipeline.

        Args:
            progress_callback: Optional callable(step, total) for progress tracking.

        Returns:
            The markdown report string (also saved to outputs/pulse_report.md).
        """
        def _tick(step: int):
            if progress_callback:
                progress_callback(step, self.TOTAL_STEPS)

        _tick(0)
        v1 = self.scan_vector_1_arxiv()
        _tick(1)

        v2 = self.scan_vector_2_tech_news()
        _tick(2)

        v3 = self.scan_vector_3_dev_community()
        _tick(3)

        report_md = self.synthesize(v1, v2, v3)
        _tick(4)

        # Prepend a header with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        full_report = f"# Market Intelligence Briefing\n_Generated: {timestamp}_\n\n{report_md}"

        # Save to outputs/
        output_path = Path("outputs") / "pulse_report.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(full_report)

        return full_report
