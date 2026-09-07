import json
import uuid
import structlog
from typing import Any, Dict, List, Optional
from google.adk.agents import LlmAgent
from google.adk import Context, Workflow
from google.adk.workflow import node

from src.config import settings
from src.agent.prompts import DIALOGUE_TTS_AGENT_INSTRUCTION
from src.agent.tools.genmedia_tools import DialogueTTSTool
from src.agent.models import (
    DialogerRequest,
    DialogerResponse,
    DialogueLine,
    VoiceProfile
)

logger = structlog.get_logger(__name__)

# -----------------------------------------------------------------------------
# Dialogue TTS Agent Definition
# -----------------------------------------------------------------------------

dialogue_tts_agent = LlmAgent(
    name='dialogue_tts_agent',
    model='gemini-2.5-flash',
    description=(
        'Extracts character dialogue from chapter text or script prose and assigns character voice personas for Gemini Flash TTS audio synthesis.'
    ),
    sub_agents=[],
    instruction=DIALOGUE_TTS_AGENT_INSTRUCTION,
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


class DialogueTTSExecutor:
    """
    Dedicated executor for Dialogue Extraction & Gemini Flash TTS Synthesis.
    Executed on-demand when requested by the user for a chapter/scene.
    """
    def __init__(self, audio_dir: str = "artifacts/media/audio"):
        self.tts_tool = DialogueTTSTool(output_dir=audio_dir)

    async def _call_llm(self, prompt: str) -> Optional[Dict[str, Any]]:
        if settings.GEMINI_API_KEY:
            try:
                from google import genai
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config={'system_instruction': DIALOGUE_TTS_AGENT_INSTRUCTION, 'temperature': 0.7}
                )
                return _parse_agent_json(response.text)
            except Exception as e:
                logger.warn("Dialogue TTS Gemini call failed, using fallback parser", error=str(e))
        return None

    async def execute(self, request: DialogerRequest) -> DialogerResponse:
        """
        Extracts dialogues from chapter text, assigns character voices, and synthesizes audio tracks.
        """
        task_id = f"dial_{uuid.uuid4().hex[:8]}"
        scene_id = f"scene_{uuid.uuid4().hex[:6]}"
        logger.info("Executing Dialogue TTS Agent", task_id=task_id, title=request.chapter_title)

        prompt_input = (
            f"Extract, segment, and direct all character dialogue lines for speech synthesis:\n"
            f"Title: {request.chapter_title}\n"
            f"Emotion Directive: {request.emotion_hint or 'natural authentic'}\n"
            f"Character Voice Hints: {json.dumps(request.character_hints or {})}\n"
            f"Segments: {json.dumps(request.segment_ids)}\n\n"
            f"Chapter Text:\n{request.chapter_text}"
        )

        agent_data = await self._call_llm(prompt_input)
        raw_dialogues = []
        if isinstance(agent_data, dict):
            raw_dialogues = agent_data.get("dialogues", [])

        # Fallback dialogue extraction from quotes if LLM is offline
        if not raw_dialogues and '"' in request.chapter_text:
            parts = request.chapter_text.split('"')
            for i in range(1, len(parts), 2):
                dial_text = parts[i].strip()
                if len(dial_text) > 2:
                    spk_name = "Character 1" if (i // 2) % 2 == 0 else "Character 2"
                    voice_name = "Aoede" if (i // 2) % 2 == 0 else "Fenrir"
                    gender = "FEMALE" if (i // 2) % 2 == 0 else "MALE"
                    if request.character_hints and spk_name in request.character_hints:
                        voice_name = request.character_hints[spk_name]
                    raw_dialogues.append({
                        "dialogueId": f"dial_{i}",
                        "speaker": spk_name,
                        "parenthetical": "speaking clearly",
                        "line": dial_text,
                        "emotion": request.emotion_hint or "expressive",
                        "voiceProfile": {
                            "voiceName": voice_name,
                            "gender": gender,
                            "speakingRate": 1.0,
                            "pitch": "+0st"
                        }
                    })

        # Synthesize audio for each dialogue line
        dialogue_models: List[DialogueLine] = []
        total_duration = 0.0

        for d in raw_dialogues:
            d_id = d.get("dialogueId", f"dial_{len(dialogue_models)+1}")
            spk = d.get("speaker", "Narrator")
            line = d.get("line", "")
            emotion = d.get("emotion", "neutral")
            vprof = d.get("voiceProfile", {})

            if request.character_hints and spk in request.character_hints:
                vprof["voice_name"] = request.character_hints[spk]

            audio_res = await self.tts_tool.generate_speech(
                scene_id=scene_id,
                dialogue_id=d_id,
                speaker=spk,
                line=line,
                emotion=emotion,
                voice_profile=vprof
            )

            dur = audio_res.get("duration_seconds", 2.0)
            total_duration += dur

            voice_profile_obj = VoiceProfile(
                voice_name=vprof.get("voiceName", vprof.get("voice_name", "Aoede")),
                gender=vprof.get("gender", "NEUTRAL"),
                speaking_rate=vprof.get("speakingRate", vprof.get("speaking_rate", 1.0)),
                pitch=vprof.get("pitch", "+0st")
            )

            dialogue_models.append(DialogueLine(
                dialogue_id=d_id,
                speaker=spk,
                speaker_entity_id=d.get("speakerEntityId"),
                listener=d.get("listener"),
                parenthetical=d.get("parenthetical"),
                line=line,
                emotion=emotion,
                voice_profile=voice_profile_obj,
                audio_path=audio_res.get("audio_path"),
                audio_url=audio_res.get("audio_url"),
                duration_seconds=dur
            ))

        return DialogerResponse(
            task_id=task_id,
            chapter_title=request.chapter_title or "Chapter Dialogues",
            dialogues=dialogue_models,
            total_lines_synthesized=len(dialogue_models),
            total_audio_duration_seconds=round(total_duration, 2),
            metadata={
                "segment_ids_processed": request.segment_ids,
                "character_hints_applied": request.character_hints
            }
        )


# Singleton instance
dialogue_tts_executor = DialogueTTSExecutor()
