"""
Tooling & Tactics — new AI products and engineering workflows.

Sources scraped via crawl4ai:
  - Ben's Bites (bensbites.com)
  - The Neuron (theneurondaily.com)
  - The Rundown AI (therundown.ai)

Date filtering is not applicable to web scraping — content is whatever
the page currently shows. The LLM synthesis step handles recency context.
"""

from .base import BaseScanner, ScanResult
from .crawl4ai_helper import crawl_urls_sync


_NEWSLETTER_URLS = [
    "https://bensbites.com",
    "https://www.theneurondaily.com",
    "https://www.therundown.ai",
]

_NEWSLETTER_NAMES = {
    "https://bensbites.com": "Ben's Bites",
    "https://www.theneurondaily.com": "The Neuron",
    "https://www.therundown.ai": "The Rundown AI",
}


class ToolingAndTacticsScanner(BaseScanner):
    MODULE_ID = "tooling_and_tactics"
    MODULE_LABEL = "Tooling & Tactics"

    def scan(self, days: int) -> ScanResult:
        crawled = crawl_urls_sync(_NEWSLETTER_URLS)
        items = [
            {
                "title": _NEWSLETTER_NAMES.get(page["url"], page["url"]),
                "content": page["content"],
                "url": page["url"],
                "source": "crawl4ai",
            }
            for page in crawled
        ]
        return ScanResult(
            module_id=self.MODULE_ID,
            module_label=self.MODULE_LABEL,
            items=items,
        )
