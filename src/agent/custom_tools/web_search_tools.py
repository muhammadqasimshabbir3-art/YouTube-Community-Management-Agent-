"""Web search tools using LangChain DuckDuckGo integration (no API key required)."""

from __future__ import annotations

import re

from langchain.tools import tool
from langchain_community.tools import DuckDuckGoSearchResults

from agent.async_utils import run_in_thread


def extract_search_query(text: str) -> str:
    """Pull a clean search query from natural-language input."""
    query = text.strip()
    query = re.sub(
        r"(?i)^(please\s+)?(search the web for|search online for|search for|look up|find)\s*",
        "",
        query,
    )
    query = re.sub(r"(?i)^(what is|who is|when is|where is)\s+", "", query)
    return query.strip(" ?.") or text.strip()


def web_search_sync(query: str, max_results: int = 5) -> str:
    """Search the web via DuckDuckGo and return formatted results."""
    search_query = extract_search_query(query)
    try:
        search_tool = DuckDuckGoSearchResults(
            num_results=max_results,
            output_format="list",
            keys_to_include=["title", "snippet", "link"],
        )
        raw = search_tool.invoke(search_query)

        if isinstance(raw, tuple):
            results, _ = raw
        else:
            results = raw

        if not results:
            return f"No web results found for '{search_query}'"

        if isinstance(results, str):
            return f"**Web Search:** {search_query}\n\n{results}"

        lines = [f"**Web Search:** {search_query}", ""]
        for index, item in enumerate(results[:max_results], start=1):
            if not isinstance(item, dict):
                lines.append(f"{index}. {item}")
                continue
            title = item.get("title", "Untitled")
            snippet = item.get("snippet", "")
            link = item.get("link", "")
            lines.append(f"{index}. **{title}**")
            if snippet:
                lines.append(f"   {snippet}")
            if link:
                lines.append(f"   {link}")
            lines.append("")

        return "\n".join(lines).strip()

    except Exception as exc:
        return (
            f"Web search error: {exc}. "
            "Install duckduckgo-search: uv add duckduckgo-search"
        )


@tool
async def web_search(query: str, max_results: int = 5) -> str:
    """Search the internet for current information, news, and facts.

    Use when the user enables web search and asks for live information.

    Args:
        query: The search query.
        max_results: Maximum number of results (default 5).

    Returns:
        Formatted web search results.
    """
    return await run_in_thread(web_search_sync, query, max_results)


__all__ = ["web_search", "web_search_sync", "extract_search_query"]
