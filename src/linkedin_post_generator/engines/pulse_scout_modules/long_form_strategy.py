"""
Long-form Strategy — high-level industry analysis and podcast content.

Sources scraped via crawl4ai:
  - Latent Space (latent.space)
  - Import AI (importai.substack.com)
  - The Algorithm / MIT Technology Review (technologyreview.com AI section)

Date filtering is not applicable to web scraping — content reflects what
the page currently shows. The LLM synthesis step handles recency context.
"""

from .base import BaseScanner, ScanResult
from .crawl4ai_helper import crawl_urls_sync


_NEWSLETTER_URLS = [
    "https://www.latent.space",
    "https://importai.substack.com",
    "https://www.technologyreview.com/topic/artificial-intelligence/",
]

_NEWSLETTER_NAMES = {
    "https://www.latent.space": "Latent Space",
    "https://importai.substack.com": "Import AI",
    "https://www.technologyreview.com/topic/artificial-intelligence/": "The Algorithm (MIT)",
}


class LongFormStrategyScanner(BaseScanner):
    MODULE_ID = "long_form_strategy"
    MODULE_LABEL = "Long-form Strategy"

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
