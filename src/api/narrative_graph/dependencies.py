"""FastAPI dependencies shared by narrative graph routes."""
from typing import TYPE_CHECKING

from fastapi import Header, HTTPException, status

from src.config import settings

if TYPE_CHECKING:
    from .service import NarrativeGraphService


def require_api_key(authorization: str | None = Header(default=None)) -> None:
    expected = settings.NARRATIVE_API_KEY
    if not expected or authorization != f"Bearer {expected}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid narrative API key")


def require_admin_api_key(authorization: str | None = Header(default=None)) -> None:
    """Protect operational controls without exposing them to writer clients."""
    expected = settings.NARRATIVE_ADMIN_API_KEY or settings.NARRATIVE_API_KEY
    if not expected or authorization != f"Bearer {expected}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid narrative admin API key")


def get_service() -> "NarrativeGraphService":
    from .service import NarrativeGraphService
    return NarrativeGraphService()
