"""Dedicated durable worker for writer agent runs."""
from __future__ import annotations

import asyncio

from src.api.narrative_graph.service import NarrativeGraphService


async def main() -> None:
    while True:
        await NarrativeGraphService().agents.execute_queued()
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
