import arxiv
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class ArxivSearchInput(BaseModel):
    query: str = Field(..., description="Search query for ArXiv papers")
    max_results: int = Field(default=5, description="Maximum number of results to return")
    sort_by: str = Field(
        default="relevance",
        description="Sort order: 'relevance' or 'date' (most recent first)",
    )


class ArxivSearchTool(BaseTool):
    name: str = "arxiv_paper_search"
    description: str = (
        "Search ArXiv for the latest AI/ML research papers. "
        "Use this to find technical breakthroughs, benchmark results, and academic citations. "
        "Returns title, authors, abstract, publication date, and PDF URL."
    )
    args_schema: type[BaseModel] = ArxivSearchInput

    def _run(self, query: str, max_results: int = 5, sort_by: str = "relevance") -> str:
        sort_criterion = (
            arxiv.SortCriterion.SubmittedDate
            if sort_by == "date"
            else arxiv.SortCriterion.Relevance
        )

        client = arxiv.Client()
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=sort_criterion,
            sort_order=arxiv.SortOrder.Descending,
        )

        results = []
        for i, paper in enumerate(client.results(search), 1):
            authors = ", ".join(a.name for a in paper.authors[:3])
            if len(paper.authors) > 3:
                authors += f" et al. ({len(paper.authors)} total)"
            abstract = paper.summary[:300].replace("\n", " ")
            if len(paper.summary) > 300:
                abstract += "..."
            results.append(
                f"{i}. **{paper.title}**\n"
                f"   Authors: {authors}\n"
                f"   Published: {paper.published.strftime('%Y-%m-%d')}\n"
                f"   Abstract: {abstract}\n"
                f"   URL: {paper.entry_id}\n"
            )

        if not results:
            return f"No ArXiv papers found for query: '{query}'"

        return f"ArXiv Search Results for '{query}':\n\n" + "\n".join(results)
