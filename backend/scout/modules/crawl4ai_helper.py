"""
Async-to-sync bridge for crawl4ai.

crawl4ai is async-native. This module runs it in a dedicated thread with a
fresh event loop, which is safe to call from Streamlit's synchronous script
thread (avoids nest_asyncio issues with Streamlit's own internals).
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor


def _run_in_new_loop(coro):
    """Execute an async coroutine in a brand-new event loop in a worker thread."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_loop_runner, coro).result()


def _loop_runner(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _crawl_all(urls: list[str]) -> list[dict]:
    """Crawl multiple URLs concurrently within one AsyncWebCrawler session."""
    try:
        from crawl4ai import AsyncWebCrawler
    except ImportError:
        return [{"url": u, "content": "crawl4ai not installed", "source": "crawl4ai"} for u in urls]

    results = []
    async with AsyncWebCrawler(verbose=False) as crawler:
        tasks = [crawler.arun(url=url) for url in urls]
        crawl_results = await asyncio.gather(*tasks, return_exceptions=True)
        for url, result in zip(urls, crawl_results):
            if isinstance(result, Exception):
                continue
            if result.success and result.markdown:
                results.append({
                    "url": url,
                    "content": result.markdown[:1500],
                    "source": "crawl4ai",
                })
    return results


def crawl_urls_sync(urls: list[str]) -> list[dict]:
    """Synchronously crawl a list of URLs and return extracted markdown content.

    Each returned dict has: url, content (up to 1500 chars), source="crawl4ai".
    Failed URLs are silently skipped. Never raises.
    """
    if not urls:
        return []
    try:
        return _run_in_new_loop(_crawl_all(urls))
    except Exception as e:
        return [{"url": u, "content": f"Crawl failed: {e}", "source": "crawl4ai"} for u in urls]
