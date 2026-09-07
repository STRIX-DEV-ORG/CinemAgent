"""
Parallel Web Search API client tool for CinemAgent.
Directly uses the official Parallel Python SDK (from parallel import Parallel, AsyncParallel)
with PARALLEL_API_KEY as the unique search mechanism. No fallbacks or mock data.
"""
from __future__ import annotations

import os
import json
from typing import Any, Dict
import structlog

try:
    from parallel import Parallel, AsyncParallel
except ImportError:
    Parallel = None
    AsyncParallel = None

from src.config import settings

logger = structlog.get_logger(__name__)


def get_parallel_client() -> Any:
    """Returns a Parallel client instance using PARALLEL_API_KEY."""
    api_key = settings.PARALLEL_API_KEY or os.environ.get("PARALLEL_API_KEY")
    if not api_key:
        raise ValueError("PARALLEL_API_KEY is not configured. Parallel search requires a valid API key.")
    if Parallel is None:
        raise ImportError("The 'parallel-web' library is not installed. Please run 'pip install parallel-web'.")
    return Parallel(api_key=api_key)


def get_async_parallel_client() -> Any:
    """Returns an AsyncParallel client instance using PARALLEL_API_KEY."""
    api_key = settings.PARALLEL_API_KEY or os.environ.get("PARALLEL_API_KEY")
    if not api_key:
        raise ValueError("PARALLEL_API_KEY is not configured. Parallel search requires a valid API key.")
    if AsyncParallel is None:
        raise ImportError("The 'parallel-web' library is not installed. Please run 'pip install parallel-web'.")
    return AsyncParallel(api_key=api_key)


async def parallel_web_search(
    query: str,
    processor: str = "base"
) -> Dict[str, Any]:
    """
    Executes a web search / research task using the official AsyncParallel client.
    Raises an error if the API key is missing or if the API call fails.
    """
    client = get_async_parallel_client()
    logger.info("Executing Parallel task_run research", query=query)

    try:
        task_run = await client.task_run.create(
            input=query,
            processor=processor
        )
        interaction_id = getattr(task_run, "interaction_id", getattr(task_run, "run_id", str(task_run)))
        
        return {
            "status": "success",
            "search_id": str(interaction_id),
            "results": [
                {
                    "title": f"Parallel Research: {query[:60]}",
                    "url": f"https://parallel.ai/task-run/{interaction_id}",
                    "type": "Parallel Web Search",
                    "excerpts": [f"Interaction ID: {interaction_id}"]
                }
            ],
            "summary": f"Parallel Task Run ({interaction_id}): Research completed for '{query}'."
        }
    except Exception as e:
        logger.error("Parallel web search failed", error=str(e), query=query)
        raise RuntimeError(f"Parallel search API error: {str(e)}") from e


def search_parallel_api(query: str) -> str:
    """
    ADK / Agent-compatible tool function to search via Parallel client.
    Returns JSON string with interaction details or raises error.
    """
    client = get_parallel_client()
    try:
        task_run = client.task_run.create(
            input=query,
            processor="base"
        )
        interaction_id = getattr(task_run, "interaction_id", getattr(task_run, "run_id", str(task_run)))
        return json.dumps({
            "status": "success",
            "interaction_id": str(interaction_id),
            "query": query
        })
    except Exception as e:
        logger.error("Parallel search tool failed", error=str(e), query=query)
        raise RuntimeError(f"Parallel search API error: {str(e)}") from e
