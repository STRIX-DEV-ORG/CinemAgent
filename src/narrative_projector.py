"""Run the narrative projector as a dedicated process in production.

Usage: ``python -m src.narrative_projector``.  It shares the same durable
checkpoint table as the in-process safety loop, so running either or both is
safe; deploy only this worker for larger production installations.
"""
from __future__ import annotations

import time

from src.api.narrative_graph.service import NarrativeGraphService


def main() -> None:
    passes = 0
    while True:
        service = NarrativeGraphService()
        service.projections.project_pending()
        passes += 1
        if passes % 20 == 0:
            service.graphs.purge_expired()
        time.sleep(3)


if __name__ == "__main__":
    main()
