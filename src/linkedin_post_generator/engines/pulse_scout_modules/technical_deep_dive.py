"""Technical Deep Dive — ArXiv research papers with time-range filtering."""

import arxiv

from .base import BaseScanner, ScanResult
from .time_utils import days_to_cutoff


class TechnicalDeepDiveScanner(BaseScanner):
    MODULE_ID = "technical_deep_dive"
    MODULE_LABEL = "Technical Deep Dive"

    def scan(self, days: int) -> ScanResult:
        cutoff = days_to_cutoff(days) if days > 0 else None
        client = arxiv.Client()
        search = arxiv.Search(
            query="(large language model OR LLM OR AI agent OR multimodal OR foundation model)",
            max_results=20,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )
        items = []
        for paper in client.results(search):
            if cutoff and paper.published < cutoff:
                # Results are descending by date — safe to stop early
                break
            items.append({
                "title": paper.title,
                "authors": [a.name for a in paper.authors[:3]],
                "abstract": paper.summary[:400].replace("\n", " "),
                "published": paper.published.strftime("%Y-%m-%d"),
                "url": paper.entry_id,
            })
            if len(items) >= 8:
                break

        return ScanResult(
            module_id=self.MODULE_ID,
            module_label=self.MODULE_LABEL,
            items=items,
        )
