import json
import uuid
import structlog
from typing import Any, Dict, Optional
from google.adk.agents import LlmAgent
from google.adk import Context, Workflow
from google.adk.workflow import node

from src.config import settings
from src.agent.prompts import SCENOGRAPHER_AGENT_INSTRUCTION
from src.agent.tools.genmedia_tools import ScenographerTool
from src.agent.models import ScenographerRequest, ScenographerResponse

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
        scene_id = f"scene_{uuid.uuid4().hex[:6]}"
        logger.info("Executing Scenographer Agent", task_id=task_id, title=request.chapter_title)

        prompt_input = (
            f"Generate a visual cinematography concept and image generation prompt for this scene/chapter:\n"
            f"Title: {request.chapter_title}\n"
            f"Genre: {request.genre}\n"
            f"Tone: {request.tone}\n"
            f"Visual Style: {request.visual_style}\n"
            f"Segments: {json.dumps(request.segment_ids)}\n\n"
            f"Chapter Text:\n{request.chapter_text}"
        )

        agent_data = await self._call_llm(prompt_input)
        concept = {}
        if isinstance(agent_data, dict):
            concept = agent_data.get("visualConcept", agent_data)

        # High quality fallback concept if offline
        if not concept:
            concept = {
                "header": f"INT. {request.chapter_title.upper()} - NIGHT",
                "shotType": "Wide cinematic anamorphic shot",
                "lighting": f"Moody {request.tone} chiaroscuro with volumetric lighting",
                "colorPalette": ["#0B132B", "#1C2541", "#3A506B", "#5BC0BE", "#F8F9FA"],
                "composition": f"Dramatic staging reflecting {request.chapter_title} narrative beat",
                "imagePrompt": f"Cinematic 35mm film still, masterpiece, {request.visual_style}, {request.chapter_title}: {request.chapter_text[:120]}, {request.tone} atmosphere, 8k resolution"
            }

        image_prompt = concept.get("imagePrompt") or f"Cinematic film still, {request.chapter_title}, {request.tone} lighting"
        header = concept.get("header") or f"INT. {request.chapter_title.upper()} - DAY"
        shot_type = concept.get("shotType") or "Cinematic Wide"
        lighting = concept.get("lighting") or f"{request.tone} lighting"
        palette = concept.get("colorPalette") or ["#0F172A", "#1E293B", "#F59E0B"]

        img_res = await self.scenographer_tool.generate_scene_image(
            scene_id=scene_id,
            image_prompt=image_prompt,
            header=header,
            shot_type=shot_type,
            lighting=lighting,
            color_palette=palette
        )

        return ScenographerResponse(
            task_id=task_id,
            scene_id=scene_id,
            chapter_title=request.chapter_title or "Chapter Scene",
            visual_concept=concept,
            image_path=img_res.get("image_path"),
            image_url=img_res.get("image_url"),
            rendered_prompt=image_prompt,
            metadata={
                "genre": request.genre,
                "tone": request.tone,
                "source": img_res.get("source", "scenographer_engine"),
                "segment_ids_processed": request.segment_ids
            }
        )


# Singleton instance
scenographer_executor = ScenographerExecutor()
