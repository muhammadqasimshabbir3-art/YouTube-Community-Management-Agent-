"""File search tools for searching files on the local system.

Provides functionality to search for files by name and content.
"""

import os
from pathlib import Path
from typing import List

from langchain.tools import tool

from agent.async_utils import run_in_thread


def _search_files_sync(
    query: str,
    search_path: str = ".",
    file_extensions: list | None = None,
    max_results: int = 10,
) -> str:
    """Search for files by name in the file system.

    Args:
        query: The search query (file name pattern)
        search_path: The path to search in (default: current directory)
        file_extensions: List of file extensions to filter by (e.g., ['.pdf', '.txt'])
        max_results: Maximum number of results to return (default 10)

    Returns:
        A formatted string containing matching files
    """
    try:
        search_path = Path(search_path).resolve()

        if not search_path.exists():
            return f"Search path does not exist: {search_path}"

        matching_files: List[Path] = []

        # Recursively search for files
        for root, dirs, files in os.walk(search_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]

            for file in files:
                # Skip hidden files
                if file.startswith("."):
                    continue

                # Check if query matches filename
                if query.lower() in file.lower():
                    # Filter by extension if specified
                    if file_extensions is None or any(
                        file.endswith(ext) for ext in file_extensions
                    ):
                        file_path = Path(root) / file
                        matching_files.append(file_path)

            if len(matching_files) >= max_results:
                break

        if not matching_files:
            return f"No files found matching '{query}' in {search_path}"

        results = [f"Found {len(matching_files)} matching files:"]
        for i, file_path in enumerate(matching_files[:max_results], 1):
            try:
                file_size = file_path.stat().st_size
                size_str = f"{file_size / 1024:.2f}KB" if file_size > 0 else "0KB"
                results.append(
                    f"{i}. {file_path.relative_to(search_path)} ({size_str})"
                )
            except Exception:
                results.append(f"{i}. {file_path.relative_to(search_path)}")

        return "\n".join(results)

    except Exception as e:
        return f"Error searching files: {str(e)}"


@tool
async def search_files(
    query: str,
    search_path: str = ".",
    file_extensions: list | None = None,
    max_results: int = 10,
) -> str:
    """Search for files by name in the file system.

    Args:
        query: The search query (file name pattern)
        search_path: The path to search in (default: current directory)
        file_extensions: List of file extensions to filter by (e.g., ['.pdf', '.txt'])
        max_results: Maximum number of results to return (default 10)

    Returns:
        A formatted string containing matching files
    """
    return await run_in_thread(
        _search_files_sync, query, search_path, file_extensions, max_results
    )


__all__ = ["search_files"]
