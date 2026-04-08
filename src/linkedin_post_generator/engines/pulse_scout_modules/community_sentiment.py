"""
Community Sentiment — Reddit, X/Twitter, TLDR AI, and Hacker News.

Tools used:
  - Tavily: Reddit (topic="news", include_domains) + X (site: operator query)
  - crawl4ai: TLDR AI newsletter scrape
  - HN Algolia API: Hacker News with UNIX timestamp filtering

Note: Tavily's `days` param is only reliable when topic="news". The X/Twitter
site: operator queries may not honour the days filter — results could exceed
the requested time window. This is a known Tavily limitation.
"""

import httpx
from tavily import TavilyClient

from .base import BaseScanner, ScanResult
from .crawl4ai_helper import crawl_urls_sync
from .time_utils import days_to_cutoff


class CommunitySentimentScanner(BaseScanner):
    MODULE_ID = "community_sentiment"
    MODULE_LABEL = "Community Sentiment"

    def __init__(self, tavily_key: str):
        self._tavily = TavilyClient(api_key=tavily_key) if tavily_key else None

    def scan(self, days: int) -> ScanResult:
        days_arg = days if days > 0 else None
        items: list[dict] = []

        # --- Reddit via Tavily (topic=news respects days filter) ---
        if self._tavily:
            try:
                resp = self._tavily.search(
                    query="AI LLM machine learning developer opinion discussion",
                    search_depth="basic",
                    topic="news",
                    include_domains=["reddit.com"],
                    days=days_arg,
                    max_results=5,
                )
                for r in resp.get("results", []):
                    items.append({
                        "title": r.get("title", ""),
                        "content": r.get("content", "")[:300],
                        "url": r.get("url", ""),
                        "source": "reddit",
                    })
            except Exception:
                pass

            # --- X/Twitter via Tavily site: operator ---
            # Note: days param may be ignored for non-news topic queries
            try:
                resp = self._tavily.search(
                    query='site:x.com AI LLM agent insights practitioners 2025',
                    search_depth="basic",
                    days=days_arg,
                    max_results=5,
                )
                for r in resp.get("results", []):
                    items.append({
                        "title": r.get("title", ""),
                        "content": r.get("content", "")[:300],
                        "url": r.get("url", ""),
                        "source": "twitter",
                    })
            except Exception:
                pass

        # --- TLDR AI via crawl4ai ---
        try:
            crawled = crawl_urls_sync(["https://tldr.tech/ai"])
            for page in crawled:
                items.append({
                    "title": "TLDR AI Latest Digest",
                    "content": page["content"][:500],
                    "url": page["url"],
                    "source": "tldr_ai",
                })
        except Exception:
            pass

        # --- Hacker News via Algolia API with unix timestamp filter ---
        try:
            params: dict = {
                "query": "AI LLM machine learning agent",
                "tags": "story",
                "hitsPerPage": 10,
                "numericFilters": "points>30",
            }
            if days_arg:
                cutoff_ts = int(days_to_cutoff(days_arg).timestamp())
                params["numericFilters"] = f"points>30,created_at_i>{cutoff_ts}"

            resp = httpx.get(
                "https://hn.algolia.com/api/v1/search_by_date",
                params=params,
                timeout=10.0,
            )
            resp.raise_for_status()
            for h in resp.json().get("hits", [])[:6]:
                items.append({
                    "title": h.get("title", ""),
                    "content": f"{h.get('points', 0)} pts, {h.get('num_comments', 0)} comments",
                    "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                    "source": "hackernews",
                })
        except Exception:
            pass

        return ScanResult(
            module_id=self.MODULE_ID,
            module_label=self.MODULE_LABEL,
            items=items,
        )
