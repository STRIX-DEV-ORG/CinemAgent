import json
import re
import uuid
import structlog
from typing import Any, Dict, List, Optional
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


_VOICE_PRESETS = ("Aoede", "Fenrir", "Puck", "Charon", "Kore")
_SPEECH_VERBS = r"said|asked|replied|answered|whispered|shouted|called|muttered|cried|told|added|snapped|sighed|yelled"


def _voice_for_speaker(speaker: str, hints: Dict[str, str], assigned_voices: Dict[str, str]) -> str:
    """Return one stable, distinct voice preset for each detected speaker."""
    if speaker.casefold() == "narrator":
        return "Kore"
    matched_name = next((name for name in hints if name.casefold() == speaker.casefold()), None)
    if matched_name:
        return hints[matched_name]
    key = speaker.casefold()
    if key not in assigned_voices:
        assigned_voices[key] = _VOICE_PRESETS[len(assigned_voices) % len(_VOICE_PRESETS)]
    return assigned_voices[key]


def _speaker_from_quote_context(before: str, after: str, known_names: List[str], previous_speaker: str | None) -> str:
    """Infer a speaker only from explicit attribution close to a quote."""
    name_pattern = r"([A-Z][A-Za-z'’-]*(?:\s+[A-Z][A-Za-z'’-]*){0,2})"
    before_patterns = (
        rf"{name_pattern}\s+(?:{_SPEECH_VERBS})\s*[,;:—-]?\s*$",
        rf"{name_pattern}\s*:\s*$",
    )
    after_patterns = (
        rf"^\s*[,;:—-]?\s*(?:{_SPEECH_VERBS})\s+{name_pattern}",
        rf"^\s*[,;:—-]?\s*{name_pattern}\s+(?:{_SPEECH_VERBS})",
    )
    for pattern in before_patterns:
        match = re.search(pattern, before, re.IGNORECASE)
        if match and match.group(1)[:1].isupper():
            return match.group(1)
    for pattern in after_patterns:
        match = re.search(pattern, after, re.IGNORECASE)
        if match and match.group(1)[:1].isupper():
            return match.group(1)
    # The graph's canonical character names are a safer fallback than making
    # up "Character 1" and "Character 2". Prefer the closest mention.
    for name in known_names:
        if re.search(rf"\b{re.escape(name)}\b", before, re.IGNORECASE):
            return name
    for name in known_names:
        if re.search(rf"\b{re.escape(name)}\b", after, re.IGNORECASE):
            return name
    return previous_speaker or "Unattributed speaker"


def _extract_attributed_dialogues(chapter_text: str, character_hints: Dict[str, str], emotion_hint: str | None) -> List[Dict[str, Any]]:
    """Extract screenplay and quoted dialogue strictly from the [character] (emotion) : "dialogue" format."""
    dialogues: List[Dict[str, Any]] = []
    assigned_voices: Dict[str, str] = {}
    
    # regex for `[character] (emotion) : "dialogue"`
    pattern = r'(?m)^\s*\[\s*(.+?)\s*\]\s*\(\s*(.+?)\s*\)\s*:\s*["“](.+?)["”]\s*$'
    
    for index, match in enumerate(re.finditer(pattern, chapter_text), start=1):
        speaker, emotion, line = match.group(1).strip(), match.group(2).strip(), match.group(3).strip()
        if line:
            dialogues.append({
                "dialogueId": f"script_{index}", "speaker": speaker, "line": line,
                "parenthetical": emotion, "emotion": emotion,
                "voiceProfile": {"voiceName": _voice_for_speaker(speaker, character_hints, assigned_voices)},
            })
    return dialogues


def _extract_passive_narration(chapter_text: str, emotion_hint: str | None) -> List[Dict[str, Any]]:
    """Return prose that is not dialogue as narrator-ready audio segments."""
    # Remove screenplay-labelled dialogue lines and quoted speech. What is
    # left is the writer's passive/descriptive narration.
    prose = re.sub(
        r"(?m)^\s*(?:\[\s*)?[A-Z][A-Za-z'’\-]*(?:\s+[A-Z][A-Za-z'’\-]*){0,2}(?:\s*\])?\s*(?:\([^\n)]*\))?\s*:\s*.*$",
        "",
        chapter_text,
    )
    prose = re.sub(r"[\"“][^\"”]+[\"”]", "", prose)
    # Do not synthesize a separate narrator clip for an attribution that has
    # no story prose of its own (for example, "Marcus replied.").
    attribution_only = re.compile(
        rf"^\s*[A-Z][A-Za-z'’\-]*(?:\s+[A-Z][A-Za-z'’\-]*){{0,2}}\s+(?:{_SPEECH_VERBS})\s*[,;:.!?—-]*\s*$",
        re.IGNORECASE,
    )
    segments: List[Dict[str, Any]] = []
    for index, sentence in enumerate(re.split(r"(?<=[.!?])\s+|\n+", prose), start=1):
        line = re.sub(r"\s+", " ", sentence).strip(" ,;:—-")
        if len(line) < 4 or attribution_only.fullmatch(line):
            continue
        segments.append({
            "dialogueId": f"narration_passage_{index}",
            "speaker": "Narrator",
            "parenthetical": "chapter narration",
            "line": line,
            "emotion": emotion_hint or "measured and cinematic",
            "voiceProfile": {"voiceName": "Kore", "gender": "NEUTRAL", "speakingRate": 1.0, "pitch": "+0st"},
        })
    return segments


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
                    model=settings.GEMINI_MODEL_VERSION,
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
            f"IMPORTANT: You must deduce the appropriate voice preset and emotion for each character based on the context (personality, tone, age, etc). Available presets: Aoede, Fenrir, Puck, Charon, Kore.\n\n"
            f"Chapter Text:\n{request.chapter_text}"
        )

        agent_data = await self._call_llm(prompt_input)
        raw_dialogues = []
        if isinstance(agent_data, dict):
            raw_dialogues = agent_data.get("dialogues", [])

        character_hints = request.character_hints or {}
        attributed_dialogues = _extract_attributed_dialogues(
            request.chapter_text,
            character_hints,
            request.emotion_hint,
        )
        # Exact text attribution is preferable to an LLM guess. It also
        # guarantees one audio artifact per quoted/script line, preserving the
        # speaking character for the writer-facing player list.
        if attributed_dialogues:
            # Merge the LLM's deduced voice profiles and emotions with the exact attributions
            llm_voices = {}
            llm_emotions = {}
            if isinstance(raw_dialogues, list):
                for d in raw_dialogues:
                    if isinstance(d, dict) and d.get("speaker"):
                        spk = d["speaker"]
                        if "voiceProfile" in d:
                            llm_voices[spk] = d["voiceProfile"]
                        if "emotion" in d:
                            llm_emotions[spk] = d["emotion"]
                            
            for ad in attributed_dialogues:
                spk = ad.get("speaker")
                if spk in llm_voices:
                    ad["voiceProfile"] = llm_voices[spk]
                if spk in llm_emotions:
                    ad["emotion"] = llm_emotions[spk]
            raw_dialogues = attributed_dialogues

        # Removed passive narration fallback logic to ensure only text with
        # the [character] (emotion) : "dialogue" structure produces audio.

        # Synthesize audio for each dialogue line
        dialogue_models: List[DialogueLine] = []
        total_duration = 0.0
        assigned_voices: Dict[str, str] = {}
        entity_ids = request.character_entity_ids or {}

        for d in raw_dialogues:
            d_id = d.get("dialogueId", f"dial_{len(dialogue_models)+1}")
            spk = str(d.get("speaker") or "Narrator").strip()
            line = str(d.get("line") or "").strip()
            if not line:
                continue
            emotion = d.get("emotion", "neutral")
            vprof = dict(d.get("voiceProfile") or {})

            voice_name = vprof.get("voice_name") or vprof.get("voiceName") or _voice_for_speaker(spk, character_hints, assigned_voices)
            vprof["voice_name"] = str(voice_name)
            vprof["gender"] = str(vprof.get("gender") or "NEUTRAL")
            vprof["speaking_rate"] = float(vprof.get("speaking_rate") or vprof.get("speakingRate") or 1.0)
            vprof["pitch"] = str(vprof.get("pitch") or "+0st")

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
                voice_name=vprof["voice_name"],
                gender=vprof.get("gender", "NEUTRAL"),
                speaking_rate=vprof["speaking_rate"],
                pitch=vprof.get("pitch", "+0st")
            )

            speaker_entity_id = d.get("speakerEntityId")
            if not speaker_entity_id:
                matched_name = next((name for name in entity_ids if name.casefold() == spk.casefold()), None)
                speaker_entity_id = entity_ids.get(matched_name) if matched_name else None

            dialogue_models.append(DialogueLine(
                dialogue_id=d_id,
                speaker=spk,
                speaker_entity_id=speaker_entity_id,
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
