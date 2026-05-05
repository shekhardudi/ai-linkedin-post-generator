import httpx
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class HNSearchInput(BaseModel):
    query: str = Field(..., description="Search query for Hacker News stories")
    max_results: int = Field(default=10, description="Maximum number of results to return")
    min_points: int = Field(default=10, description="Minimum number of upvotes to filter noise")


class HNSearchTool(BaseTool):
    name: str = "hacker_news_search"
    description: str = (
        "Search Hacker News (via Algolia API) for developer community discussions, "
        "trending AI tools, and engineer sentiment. Free — no API key required. "
        "Returns title, URL, points, comment count, and date."
    )
    args_schema: type[BaseModel] = HNSearchInput

    def _run(self, query: str, max_results: int = 10, min_points: int = 10) -> str:
        url = "https://hn.algolia.com/api/v1/search_by_date"
        params = {
            "query": query,
            "tags": "story",
            "hitsPerPage": max_results * 2,  # over-fetch to allow filtering by points
        }

        try:
            response = httpx.get(url, params=params, timeout=10.0)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            return f"HN search failed: {e}"

        hits = [h for h in data.get("hits", []) if (h.get("points") or 0) >= min_points]
        hits = hits[:max_results]

        if not hits:
            return f"No Hacker News stories found for query: '{query}' (min {min_points} points)"

        results = []
        for i, hit in enumerate(hits, 1):
            title = hit.get("title", "Untitled")
            hn_url = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
            external_url = hit.get("url", hn_url)
            points = hit.get("points", 0)
            comments = hit.get("num_comments", 0)
            created = (hit.get("created_at") or "")[:10]
            results.append(
                f"{i}. **{title}**\n"
                f"   Points: {points} | Comments: {comments} | Date: {created}\n"
                f"   Link: {external_url}\n"
                f"   HN: {hn_url}\n"
            )

        return f"Hacker News Results for '{query}':\n\n" + "\n".join(results)
