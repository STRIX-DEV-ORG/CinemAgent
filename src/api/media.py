"""
Media API router for CinemAgent.
Provides REST endpoints to download, stream, and inspect images and audio
stored within ClickHouse source_segment records.
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Response, Query
from pydantic import BaseModel, Field

from src.db.clickhouse_client import (
    get_segment_media,
    get_segment_all_media,
    save_segment_media
)

router = APIRouter(prefix="/api/v1/media", tags=["Media"])


class SegmentMediaUploadRequest(BaseModel):
    image_data: Optional[str] = Field(default=None, description="Base64-encoded image bitmap or string")
    image_mime: str = Field(default="image/png", description="MIME type for image e.g. image/png, image/jpeg")
    audio_data: Optional[str] = Field(default=None, description="Base64-encoded audio binary or string")
    audio_mime: str = Field(default="audio/wav", description="MIME type for audio e.g. audio/wav, audio/mp3")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Custom metadata tags")


class SegmentMediaInfoResponse(BaseModel):
    segment_id: str
    graph_id: Optional[str] = None
    chapter: Optional[int] = None
    sequence: Optional[int] = None
    has_image: bool
    image_mime: Optional[str] = None
    image_size_bytes: int = 0
    image_download_url: Optional[str] = None
    has_audio: bool
    audio_mime: Optional[str] = None
    audio_size_bytes: int = 0
    audio_download_url: Optional[str] = None
    media_metadata: Dict[str, str] = Field(default_factory=dict)


@router.get("/segment/{segment_id}", response_model=SegmentMediaInfoResponse)
def get_segment_media_info(segment_id: str):
    """
    Retrieves information and download URLs for media attached to a source segment.
    """
    try:
        info = get_segment_all_media(segment_id)
        if not info:
            raise HTTPException(status_code=404, detail=f"Source segment '{segment_id}' not found.")
        
        return SegmentMediaInfoResponse(
            segment_id=info["segment_id"],
            graph_id=info.get("graph_id"),
            chapter=info.get("chapter"),
            sequence=info.get("sequence"),
            has_image=info["has_image"],
            image_mime=info.get("image_mime"),
            image_size_bytes=info.get("image_size_bytes", 0),
            image_download_url=f"/api/v1/media/segment/{segment_id}/image" if info["has_image"] else None,
            has_audio=info["has_audio"],
            audio_mime=info.get("audio_mime"),
            audio_size_bytes=info.get("audio_size_bytes", 0),
            audio_download_url=f"/api/v1/media/segment/{segment_id}/audio" if info["has_audio"] else None,
            media_metadata=info.get("media_metadata", {})
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch segment media info: {str(e)}")


@router.get("/segment/{segment_id}/image")
def download_segment_image(segment_id: str, download: bool = Query(default=False, description="Force file attachment download")):
    """
    Streams or downloads the image bitmap associated with a source segment.
    """
    try:
        media = get_segment_media(segment_id, media_type="image")
        if not media or not media[0]:
            raise HTTPException(status_code=404, detail=f"No image media found for segment '{segment_id}'.")
        
        image_bytes, mime = media
        headers = {}
        if download:
            ext = mime.split("/")[-1] if "/" in mime else "png"
            headers["Content-Disposition"] = f'attachment; filename="segment_{segment_id}.{ext}"'

        return Response(content=image_bytes, media_type=mime, headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve segment image: {str(e)}")


@router.get("/segment/{segment_id}/audio")
def download_segment_audio(segment_id: str, download: bool = Query(default=False, description="Force file attachment download")):
    """
    Streams or downloads the audio file associated with a source segment.
    """
    try:
        media = get_segment_media(segment_id, media_type="audio")
        if not media or not media[0]:
            raise HTTPException(status_code=404, detail=f"No audio media found for segment '{segment_id}'.")
        
        audio_bytes, mime = media
        headers = {}
        if download:
            ext = mime.split("/")[-1] if "/" in mime else "wav"
            headers["Content-Disposition"] = f'attachment; filename="segment_{segment_id}.{ext}"'

        return Response(content=audio_bytes, media_type=mime, headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve segment audio: {str(e)}")


@router.post("/segment/{segment_id}")
def upload_segment_media(segment_id: str, payload: SegmentMediaUploadRequest):
    """
    Uploads or attaches media (image bitmaps and audio) directly to a source segment.
    """
    try:
        success = save_segment_media(
            segment_id=segment_id,
            image_data=payload.image_data,
            image_mime=payload.image_mime,
            audio_data=payload.audio_data,
            audio_mime=payload.audio_mime,
            metadata=payload.metadata
        )
        return {
            "status": "success",
            "segment_id": segment_id,
            "message": "Media successfully attached to source segment."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save segment media: {str(e)}")
