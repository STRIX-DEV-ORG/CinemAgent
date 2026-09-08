import json
import re
import uuid
import structlog
from typing import Any, Dict, List, Optional
from google.adk.agents import LlmAgent
from google.adk import Context, Workflow
from google.adk.workflow import node

from src.config import settings
from src.agent.prompts import SCENOGRAPHER_AGENT_INSTRUCTION
from src.agent.tools.genmedia_tools import ScenographerTool
from src.agent.models import ScenographerRequest, ScenographerResponse, StoryboardScene

logger = structlog.get_logger(__name__)

# -----------------------------------------------------------------------------
# Scenographer Agent Definition
# -----------------------------------------------------------------------------

scenographer_agent = LlmAgent(
    name='scenographer_agent',
    model='gemini-2.5-flash',
    description=(
        'Translates chapter text, scene blueprints, and script prose into cinematic visual storyboard specifications and image generation prompts.'
    ),
    sub_agents=[],
    instruction=SCENOGRAPHER_AGENT_INSTRUCTION,
    tools=[],
)


def _parse_agent_json(result: Any) -> Any:
    if isinstance(result, str):
        try:
            cleaned = result.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            return json.loads(cleaned.strip())
        except json.JSONDecodeError:
            return result
    return result


def _split_chapter_into_scenes(chapter_text: str, limit: int = 6) -> List[tuple[str, str, str]]:
    """Split screenplay headers or prose scene transitions into visual beats."""
    text = chapter_text.strip()
    if not text:
        return []
    header_pattern = re.compile(r"(?mi)^\s*((?:INT\.|EXT\.|INT/EXT\.|I/E\.).+)$")
    headers = list(header_pattern.finditer(text))
    if headers:
        scenes = []
        for index, header_match in enumerate(headers, start=1):
            end = headers[index].start() if index < len(headers) else len(text)
            excerpt = text[header_match.end():end].strip()
            if excerpt:
                header = header_match.group(1).strip()
                scenes.append((f"Scene {index}", header, excerpt))
        return scenes[:limit] or [("Scene 1", f"INT. CHAPTER - DAY", text)]

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n|\n\s*(?:\*{3,}|-{3,}|#{2,})\s*\n", text) if part.strip()]
    if not paragraphs:
        paragraphs = [text]
    scenes: List[tuple[str, str, str]] = []
    current: List[str] = []
    for paragraph in paragraphs:
        transition = bool(re.match(r"(?i)^(?:later|meanwhile|elsewhere|at dawn|at dusk|that night|the next day|hours later|by morning)\b", paragraph))
        if current and (transition or len("\n\n".join(current)) + len(paragraph) > 1100 or len(current) >= 3):
            excerpt = "\n\n".join(current)
            scenes.append((f"Scene {len(scenes) + 1}", f"CHAPTER BEAT {len(scenes) + 1}", excerpt))
            current = []
        current.append(paragraph)
    if current and len(scenes) < limit:
        scenes.append((f"Scene {len(scenes) + 1}", f"CHAPTER BEAT {len(scenes) + 1}", "\n\n".join(current)))
    return scenes[:limit]


class ScenographerExecutor:
    """
    Dedicated executor for the Scenographer Agent.
    Executed on-demand when requested by the user for a chapter/scene.
    """
    def __init__(self, images_dir: str = "artifacts/media/images"):
        self.scenographer_tool = ScenographerTool(output_dir=images_dir)

    async def _call_llm(self, prompt: str) -> Optional[Dict[str, Any]]:
        if settings.GEMINI_API_KEY:
            try:
                from google import genai
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config={'system_instruction': SCENOGRAPHER_AGENT_INSTRUCTION, 'temperature': 0.7}
                )
                return _parse_agent_json(response.text)
            except Exception as e:
                logger.warn("Scenographer Gemini call failed, using fallback concept", error=str(e))
        return None

    async def execute(self, request: ScenographerRequest) -> ScenographerResponse:
        """
        Executes Scenographer visual concept formulation and image rendering for a chapter.
        """
        task_id = f"sceno_{uuid.uuid4().hex[:8]}"
        logger.info("Executing Scenographer Agent", task_id=task_id, title=request.chapter_title)

        scenes: List[StoryboardScene] = []
        for index, (scene_title, detected_header, scene_text) in enumerate(
            _split_chapter_into_scenes(request.chapter_text), start=1
        ):
            scene_id = f"{task_id}_scene_{index}"
            prompt_input = (
                f"Generate a visual cinematography concept and image generation prompt for this one scene. "
                f"Do not include events from any other scene.\n"
                f"Chapter: {request.chapter_title}\nScene: {scene_title}\nDetected header: {detected_header}\n"
                f"Genre: {request.genre}\nTone: {request.tone}\nVisual Style: {request.visual_style}\n"
                f"Segments: {json.dumps(request.segment_ids)}\n\n"
                f"VISUAL CANON (use details only when relevant to this scene; render them visibly):\n"
                f"{json.dumps(request.storyboard_context, ensure_ascii=False)}\n\nScene Text:\n{scene_text}"
            )
            agent_data = await self._call_llm(prompt_input)
            concept = agent_data.get("visualConcept", agent_data) if isinstance(agent_data, dict) else {}
            if not concept:
                concept = {
                    "header": detected_header,
                    "shotType": "Wide cinematic anamorphic shot",
                    "lighting": f"Moody {request.tone} chiaroscuro with volumetric lighting",
                    "colorPalette": ["#0B132B", "#1C2541", "#3A506B", "#5BC0BE", "#F8F9FA"],
                    "composition": f"Dramatic staging reflecting {scene_title}",
                    "imagePrompt": f"Cinematic 35mm film still, masterpiece, {request.visual_style}. Depict only this exact scene, including its characters, setting, named objects, and action: {scene_text[:1600]}. Visual canon (do not contradict; make relevant details visible): {json.dumps(request.storyboard_context, ensure_ascii=False)[:1800]}. Tone: {request.tone}."
                }
            image_prompt = concept.get("imagePrompt") or f"Cinematic film still, {scene_title}, {request.tone} lighting"
            header = concept.get("header") or detected_header
            shot_type = concept.get("shotType") or "Cinematic Wide"
            lighting = concept.get("lighting") or f"{request.tone} lighting"
            palette = concept.get("colorPalette") or ["#0F172A", "#1E293B", "#F59E0B"]
            img_res = await self.scenographer_tool.generate_scene_image(
                scene_id=scene_id,
                image_prompt=image_prompt,
                scene_text=scene_text,
                header=header,
                shot_type=shot_type,
                lighting=lighting,
                color_palette=palette,
            )
            scenes.append(StoryboardScene(
                scene_id=scene_id,
                title=scene_title,
                header=header,
                excerpt=scene_text[:500],
                visual_concept=concept,
                image_path=img_res.get("image_path"),
                image_url=img_res.get("image_url"),
                rendered_prompt=image_prompt,
            ))

        if not scenes:
            raise ValueError("write chapter text before generating a storyboard")
        primary_scene = scenes[0]

        return ScenographerResponse(
            task_id=task_id,
            scene_id=primary_scene.scene_id,
            chapter_title=request.chapter_title or "Chapter Scene",
            visual_concept=primary_scene.visual_concept,
            image_path=primary_scene.image_path,
            image_url=primary_scene.image_url,
            rendered_prompt=primary_scene.rendered_prompt,
            scenes=scenes,
            metadata={
                "genre": request.genre,
                "tone": request.tone,
                "scene_count": len(scenes),
                "segment_ids_processed": request.segment_ids,
            }
        )


# Singleton instance
scenographer_executor = ScenographerExecutor()
