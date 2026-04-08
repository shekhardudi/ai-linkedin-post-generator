"""
Expert Synthesis — curated industry summaries via Tavily domain-specific search.

Sources: The Batch (deeplearning.ai), HuggingFace weekly, general weekly roundups.
Uses Tavily advanced search with include_domains for precision targeting.
"""

from tavily import TavilyClient

from .base import BaseScanner, ScanResult


class ExpertSynthesisScanner(BaseScanner):
    MODULE_ID = "expert_synthesis"
    MODULE_LABEL = "Expert Synthesis"

    def __init__(self, tavily_key: str):
        self._tavily = TavilyClient(api_key=tavily_key) if tavily_key else None

    def scan(self, days: int) -> ScanResult:
        if not self._tavily:
            return ScanResult(self.MODULE_ID, self.MODULE_LABEL, [],
                              error="Tavily API key not set")

        days_arg = days if days > 0 else None
        items: list[dict] = []

        # --- The Batch + HuggingFace domain search ---
        try:
            resp = self._tavily.search(
                query="AI weekly summary insights analysis trends",
                search_depth="advanced",
                topic="news",
                include_domains=["deeplearning.ai", "huggingface.co"],
                days=days_arg,
                max_results=6,
            )
            for r in resp.get("results", []):
                items.append({
                    "title": r.get("title", ""),
                    "content": r.get("content", "")[:300],
                    "url": r.get("url", ""),
                    "source": "expert_curated",
                })
        except Exception:
            pass

        # --- Broader weekly roundup search ---
        try:
            resp = self._tavily.search(
                query="AI weekly roundup report key developments",
                search_depth="basic",
                topic="news",
                days=days_arg,
                max_results=4,
            )
            for r in resp.get("results", []):
                items.append({
                    "title": r.get("title", ""),
                    "content": r.get("content", "")[:300],
                    "url": r.get("url", ""),
                    "source": "weekly_roundup",
                })
        except Exception:
            pass

        return ScanResult(
            module_id=self.MODULE_ID,
            module_label=self.MODULE_LABEL,
            items=items,
        )
