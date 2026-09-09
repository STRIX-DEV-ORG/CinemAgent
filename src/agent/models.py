import time
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class VoiceProfile(BaseModel):
    voice_name: str = Field(default="Aoede", description="Voice identifier e.g. Aoede, Fenrir, Puck, Charon, Kore")
    gender: str = Field(default="NEUTRAL", description="Voice gender profile: FEMALE, MALE, NEUTRAL")
    speaking_rate: float = Field(default=1.0, description="Speed multiplier from 0.5 to 2.0")
    pitch: str = Field(default="+0st", description="Pitch adjustment e.g. +0st, -2st, +3st")


class DialogueLine(BaseModel):
    dialogue_id: str
    speaker: str
    speaker_entity_id: Optional[str] = None
    listener: Optional[str] = None
    parenthetical: Optional[str] = None
    line: str
    emotion: Optional[str] = None
    voice_profile: Optional[VoiceProfile] = None
    audio_path: Optional[str] = None
    audio_url: Optional[str] = None
    duration_seconds: Optional[float] = None


class VisualConcept(BaseModel):
    header: Optional[str] = None
    shot_type: Optional[str] = None
    lighting: Optional[str] = None
    color_palette: List[str] = Field(default_factory=list)
    composition: Optional[str] = None
    image_prompt: str


class SceneMediaArtifact(BaseModel):
    scene_id: str
    scene_title: Optional[str] = None
    scene_header: Optional[str] = "INT. SCENE - DAY"
    visual_concept: Optional[VisualConcept] = None
    image_path: Optional[str] = None
    image_url: Optional[str] = None
    dialogues: List[DialogueLine] = Field(default_factory=list)
    prose: Optional[str] = None


class PipelineProgressStatus(BaseModel):
    task_id: str
    status_value: int = Field(default=0, ge=0, le=100, description="Progress percentage from 0 to 100")
    status_message: str = Field(default="Initialized pipeline", description="User-facing status message")
    current_agent: str = Field(default="Orchestrator", description="Active agent performing the current step")
    stage: str = Field(
        default="idle", 
        description="Current stage: idle, text_to_graph, graph_to_text, gen_media, pdf_export, completed, error"
    )
    is_completed: bool = False
    is_error: bool = False
    error_message: Optional[str] = None
    artifacts: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class ScreenplayPipelineRequest(BaseModel):
    graph_id: Optional[UUID] = Field(default=None, description="Required target story UUID for the durable pipeline.")
    chapter_id: Optional[UUID] = Field(default=None, description="Optional chapter UUID; omit for story production.")
    raw_text: Optional[str] = Field(
        default=None, 
        description="Raw narrative or screenplay text to ingest via Text-to-Graph pipeline."
    )
    story_prompt: Optional[str] = Field(
        default=None, 
        description="Natural language instruction to guide Graph-to-Text story generation."
    )
    genre: str = Field(default="cinematic mystery", description="Target genre of the screenplay")
    tone: str = Field(default="suspenseful, visual", description="Target mood and dramatic tone")
    enable_images: bool = Field(default=True, description="Enable Scenographer image storyboard generation")
    enable_tts: bool = Field(default=True, description="Enable Gemini Flash TTS dialogue audio generation")
    enable_pdf: bool = Field(default=True, description="Generate downloadable formatted screenplay PDF")


# -----------------------------------------------------------------------------
# Standalone Agent Requests & Responses (Triggered via UI Buttons)
# -----------------------------------------------------------------------------

class ScenographerRequest(BaseModel):
    chapter_text: str = Field(..., description="The narrative or script text of the chapter/scene to convert into visual storyboards.")
    chapter_title: Optional[str] = Field(default="Scene Visual", description="Title or header of the scene/chapter")
    segment_ids: List[str] = Field(default_factory=list, description="Optional segment IDs from script ingestion")
    genre: Optional[str] = Field(default="cinematic drama", description="Film genre e.g. sci-fi, period drama, noir")
    tone: Optional[str] = Field(default="atmospheric", description="Lighting / mood tone e.g. chiaroscuro, golden hour, neon noir")
    visual_style: Optional[str] = Field(default="Cinematic 35mm film still, anamorphic lens, masterpiece", description="Visual styling directives")
    aspect_ratio: Optional[str] = Field(default="16:9", description="Aspect ratio of the generated storyboard image")
    storyboard_context: Dict[str, Any] = Field(default_factory=dict, description="Canonical character, setting, object, and fact details from the narrative graph")


class StoryboardScene(BaseModel):
    scene_id: str
    title: str
    header: str
    excerpt: str
    visual_concept: Dict[str, Any]
    image_path: Optional[str] = None
    image_url: Optional[str] = None
    rendered_prompt: str


class ScenographerResponse(BaseModel):
    task_id: str
    scene_id: str
    chapter_title: str
    visual_concept: Dict[str, Any]
    image_path: Optional[str] = None
    image_url: Optional[str] = None
    rendered_prompt: str
    scenes: List[StoryboardScene] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DialogerRequest(BaseModel):
    chapter_text: str = Field(..., description="The script or narrative chapter containing character dialogues to extract and voice.")
    chapter_title: Optional[str] = Field(default="Dialogue Track", description="Title of the scene/chapter")
    segment_ids: List[str] = Field(default_factory=list, description="Optional segment IDs")
    character_hints: Optional[Dict[str, str]] = Field(default=None, description="Optional map of Character Name to Voice Name (e.g. {'Elena': 'Aoede', 'Marcus': 'Fenrir'})")
    character_entity_ids: Optional[Dict[str, str]] = Field(default=None, description="Optional map of character names to their narrative graph entity IDs")
    emotion_hint: Optional[str] = Field(default=None, description="Overall emotional directive e.g. 'tense whisper', 'confrontational'")


class DialogerResponse(BaseModel):
    task_id: str
    chapter_title: str
    dialogues: List[DialogueLine]
    total_lines_synthesized: int
    total_audio_duration_seconds: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


class InvestigatorRequest(BaseModel):
    query: str = Field(..., description="The query or scene text to investigate for historical accuracy, anachronisms, or lore consistency.")
    era_context: Optional[str] = Field(default=None, description="Optional historical era (e.g., '14th Century Venice', 'Victorian London', 'Feudal Japan')")
    genre: Optional[str] = Field(default="historical fiction", description="Story genre or universe context")


class InvestigatorResponse(BaseModel):
    task_id: str
    query: str
    verdict: str = Field(description="Verdict: HISTORICALLY_ACCURATE, ANACHRONISTIC, PLAUSIBLE_CREATIVE_LICENSE, FACTUALLY_INCORRECT")
    confidence_score: float = Field(default=0.9, ge=0.0, le=1.0)
    era_analyzed: Optional[str] = None
    historical_summary: str
    detected_anachronisms: List[Dict[str, Any]] = Field(default_factory=list)
    recommendations_for_writers: str
    search_sources: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

