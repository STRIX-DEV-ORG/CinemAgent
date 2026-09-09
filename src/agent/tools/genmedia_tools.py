import os
import asyncio
import base64
import subprocess
import structlog
import wave
import math
import struct
import re
import binascii
from pathlib import Path
from typing import Dict, Any, Optional, List
from PIL import Image, ImageDraw, ImageFont

from src.config import settings

logger = structlog.get_logger(__name__)


def _binary_data(value: Any) -> bytes:
    """Accept SDK bytes or the base64 payload exposed by Interactions."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        try:
            return base64.b64decode(value)
        except (ValueError, binascii.Error) as error:
            raise ValueError("Gemini returned an invalid base64 media payload") from error
    raise ValueError("Gemini did not return binary media data")


def _write_pcm_wav(path: str, pcm: bytes, rate: int = 24_000) -> None:
    """Gemini TTS returns raw 16-bit PCM, not a ready-to-play WAV container."""
    with wave.open(path, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(pcm)


def _create_mock_storyboard_image(
    output_path: str,
    scene_id: str,
    header: str,
    shot_type: str,
    lighting: str,
    prompt: str,
    scene_text: str = "",
    color_palette: Optional[List[str]] = None
) -> str:
    """Render a chapter-aware illustrated storyboard when Imagen is unavailable."""
    width, height = 1280, 720
    palette = color_palette or ["#0D1117", "#161B22", "#D5CEA3", "#E5BA73"]
    
    # Parse primary bg color
    def hex_to_rgb(hex_code):
        hex_clean = hex_code.lstrip("#")
        if len(hex_clean) == 6:
            return tuple(int(hex_clean[i:i+2], 16) for i in (0, 2, 4))
        return (20, 24, 33)

    bg_color = hex_to_rgb(palette[0]) if palette else (15, 20, 28)
    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    visual_text = f"{scene_text} {prompt}".casefold()
    named_characters = []
    for name in re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", scene_text):
        if name not in named_characters and name not in {"The", "And", "But", "Chapter"}:
            named_characters.append(name)
    named_characters = named_characters[:3] or ["Narrator"]
    setting = (
        "market" if "market" in visual_text else "forest" if "forest" in visual_text else
        "shore" if any(word in visual_text for word in ("sea", "ocean", "shore", "ship")) else
        "castle" if any(word in visual_text for word in ("castle", "palace", "tower")) else
        "city" if any(word in visual_text for word in ("city", "street", "alley")) else "interior"
    )
    is_night = any(word in visual_text for word in ("night", "moon", "dark", "midnight"))
    has_rain = any(word in visual_text for word in ("rain", "storm", "wet", "thunder"))
    has_fire = any(word in visual_text for word in ("fire", "flame", "burn", "torch"))

    # 1. Draw a location-specific cinematic sky and horizon.
    accent_rgb = hex_to_rgb(palette[-1]) if palette else (229, 186, 115)
    for y in range(height):
        ratio = y / height
        r = int(bg_color[0] * (1 - ratio * 0.7) + accent_rgb[0] * (ratio * 0.3))
        g = int(bg_color[1] * (1 - ratio * 0.7) + accent_rgb[1] * (ratio * 0.3))
        b = int(bg_color[2] * (1 - ratio * 0.7) + accent_rgb[2] * (ratio * 0.3))
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    horizon = 450
    ground = (23, 31, 42) if is_night else (72, 66, 53)
    draw.rectangle([(0, horizon), (width, height)], fill=ground)
    if setting == "market":
        for x in range(80, width, 220):
            draw.rectangle([(x, 290), (x + 150, horizon)], fill=(48, 38, 33), outline=(172, 127, 72))
            draw.polygon([(x - 15, 290), (x + 75, 220), (x + 165, 290)], fill=(122, 54, 43))
    elif setting == "forest":
        for x in range(70, width, 155):
            draw.rectangle([(x, 180), (x + 35, horizon)], fill=(35, 44, 31))
            draw.ellipse([(x - 65, 100), (x + 105, 300)], fill=(29, 61, 44))
    elif setting == "shore":
        draw.rectangle([(0, 340), (width, horizon)], fill=(33, 83, 111))
        for y in range(355, horizon, 26):
            draw.arc([(0, y - 18), (width, y + 18)], 180, 355, fill=(174, 211, 225), width=3)
    elif setting == "castle":
        draw.rectangle([(360, 190), (900, horizon)], fill=(62, 62, 76))
        for x in (390, 590, 790):
            draw.rectangle([(x, 105), (x + 90, 300)], fill=(69, 69, 82))
            draw.polygon([(x - 15, 105), (x + 45, 35), (x + 105, 105)], fill=(48, 43, 57))
    elif setting == "city":
        for x in range(0, width, 115):
            building_height = 130 + (x * 37 % 170)
            draw.rectangle([(x, horizon - building_height), (x + 95, horizon)], fill=(37, 43, 58))
            for window_y in range(horizon - building_height + 20, horizon - 15, 35):
                draw.rectangle([(x + 20, window_y), (x + 30, window_y + 12)], fill=(232, 187, 92))
    else:
        draw.rectangle([(120, 180), (1160, horizon)], fill=(55, 49, 48), outline=(129, 103, 74), width=5)
        draw.rectangle([(520, 250), (760, horizon)], fill=(30, 28, 31))

    # Place the chapter's characters in the foreground as story-specific silhouettes.
    for index, character in enumerate(named_characters):
        x = 380 + index * 240
        head_y = 355 - index * 12
        silhouette = (17, 20, 29) if is_night else (42, 38, 38)
        draw.ellipse([(x - 28, head_y - 55), (x + 28, head_y)], fill=silhouette)
        draw.polygon([(x - 62, head_y + 115), (x + 62, head_y + 115), (x + 35, head_y), (x - 35, head_y)], fill=silhouette)
        draw.text((x - 55, head_y + 130), character[:18].upper(), fill=(242, 225, 181))
    if has_rain:
        for x in range(40, width, 42):
            draw.line([(x, 90), (x - 35, horizon)], fill=(137, 182, 206), width=2)
    if has_fire:
        for x in range(180, width, 310):
            draw.polygon([(x, horizon), (x + 22, horizon - 90), (x + 45, horizon)], fill=(245, 126, 43))
            draw.polygon([(x + 12, horizon), (x + 24, horizon - 52), (x + 34, horizon)], fill=(255, 218, 95))

    # 2. Cinematic letterbox bars
    bar_height = 60
    draw.rectangle([(0, 0), (width, bar_height)], fill=(5, 5, 8))
    draw.rectangle([(0, height - bar_height), (width, height)], fill=(5, 5, 8))

    # 3. Frame and chapter-derived beat caption.
    draw.rectangle([(40, bar_height + 20), (width - 40, height - bar_height - 20)], outline=(80, 100, 130), width=2)
    
    # 4. Text annotations identify the actual chapter setting and beat.
    title_text = f"CINEMAGENT STORYBOARD — {scene_id.upper()}"
    header_text = header or "INT. CINEMATIC SCENE - NIGHT"
    shot_text = f"SHOT TYPE: {shot_type or 'Cinematic Wide'}"
    light_text = f"LIGHTING: {lighting or 'Atmospheric Moody Chiaroscuro'}"
    
    draw.text((60, 20), title_text, fill=(230, 230, 240))
    draw.text((width - 340, 20), f"CHAPTER SCENE: {setting.upper()}", fill=(200, 180, 120))
    
    draw.text((60, bar_height + 40), header_text, fill=(255, 235, 170))
    draw.text((60, bar_height + 75), shot_text, fill=(180, 200, 220))
    draw.text((60, bar_height + 105), light_text, fill=(160, 180, 200))

    # Prompt box at bottom
    prompt_box_y = height - bar_height - 110
    draw.rectangle([(60, prompt_box_y), (width - 60, height - bar_height - 30)], fill=(10, 14, 20), outline=(60, 80, 110))
    
    beat = " ".join(scene_text.split())[:180] or prompt[:180]
    draw.text((75, prompt_box_y + 15), "CHAPTER BEAT:", fill=(229, 186, 115))
    draw.text((75, prompt_box_y + 40), beat, fill=(210, 215, 225))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "PNG")
    return output_path


def _create_mock_wav_audio(
    output_path: str, 
    duration_seconds: float = 2.5, 
    base_freq: float = 220.0
) -> str:
    """
    Generates a clean playable PCM WAV audio file with melodic voice modulation
    when offline or as a reliable synthesized fallback.
    """
    sample_rate = 24000
    total_samples = int(sample_rate * duration_seconds)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with wave.open(output_path, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)

        data = []
        for i in range(total_samples):
            t = float(i) / sample_rate
            # Speech formant envelope simulation
            vowel_mod = 1.0 + 0.3 * math.sin(2.0 * math.pi * 5.0 * t)
            freq = base_freq * vowel_mod + 20 * math.sin(2.0 * math.pi * 1.5 * t)
            
            # Attack and decay envelope
            envelope = min(t / 0.1, (duration_seconds - t) / 0.2, 1.0)
            envelope = max(0.0, envelope)
            
            sample_val = 16000.0 * envelope * (
                0.6 * math.sin(2.0 * math.pi * freq * t) +
                0.3 * math.sin(4.0 * math.pi * freq * t) +
                0.1 * math.sin(6.0 * math.pi * freq * t)
            )
            packed_sample = struct.pack('<h', int(max(-32767, min(32767, sample_val))))
            data.append(packed_sample)

        wav_file.writeframes(b''.join(data))

    return output_path


def _synthesize_windows_speech(output_path: str, text: str, emotion: str) -> bool:
    """Create actual spoken narration with the Windows SAPI voice when cloud TTS is unavailable."""
    if os.name != "nt" or not text.strip():
        return False
    encoded_text = base64.b64encode(text.encode("utf-16-le")).decode("ascii")
    encoded_path = base64.b64encode(os.path.abspath(output_path).encode("utf-16-le")).decode("ascii")
    rate = {"slow": -2, "calm": -1, "excited": 2, "angry": 1}.get(emotion.casefold(), 0)
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$voice.Rate = {rate}; "
        f"$path = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{encoded_path}')); "
        f"$text = [Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{encoded_text}')); "
        "$voice.SetOutputToWaveFile($path); $voice.Speak($text); $voice.Dispose()"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=max(30, len(text) // 3),
            check=False,
        )
        if completed.returncode == 0 and Path(output_path).is_file() and Path(output_path).stat().st_size > 1024:
            return True
        logger.warning("Windows SAPI narration failed", error=completed.stderr.strip())
    except Exception as error:
        logger.warning("Windows SAPI narration unavailable", error=str(error))
    return False


async def _synthesize_edge_speech(output_path: str, text: str, voice_name: str) -> bool:
    """Use Microsoft Edge's neural speech service and save an MP3 narration."""
    voice_map = {
        "aoede": "en-US-AvaMultilingualNeural",
        "fenrir": "en-US-AndrewMultilingualNeural",
        "puck": "en-GB-SoniaNeural",
        "charon": "en-US-BrianMultilingualNeural",
        "kore": "en-US-EmmaMultilingualNeural",
    }
    try:
        import edge_tts
        voice = voice_map.get(voice_name.casefold(), "en-US-AvaMultilingualNeural")
        communicator = edge_tts.Communicate(
            text,
            voice=voice,
        )
        await communicator.save(output_path)
        return Path(output_path).is_file() and Path(output_path).stat().st_size > 1024
    except Exception as error:
        logger.warning("Edge neural narration failed", error=str(error))
        return False


class ScenographerTool:
    """
    Generates visual storyboard framing and keyframes for scenes
    using Google GenAI Imagen / Gemini or high-definition visual generation.
    """
    def __init__(self, output_dir: str = "artifacts/media/images"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate_scene_image(
        self,
        scene_id: str,
        image_prompt: str,
        scene_text: str = "",
        header: str = "",
        shot_type: str = "Cinematic Wide",
        lighting: str = "Low-key chiaroscuro",
        color_palette: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Creates a storyboard image from the Scenographer's visual concept.
        """
        filename = f"{scene_id}_storyboard.png"
        output_file = str(self.output_dir / filename)
        
        logger.info("Scenographer generating scene image", scene_id=scene_id, prompt=image_prompt[:80])

        if settings.GEMINI_API_KEY:
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
            except Exception as error:
                raise RuntimeError(f"Gemini image client could not start: {error}") from error
            try:
                result = client.models.generate_content(
                    model=settings.GEMINI_IMAGE_MODEL, contents=image_prompt,
                    config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"], image_config=types.ImageConfig(aspect_ratio="16:9")),
                )
                for part in getattr(getattr(result.candidates[0], "content", None), "parts", []) or []:
                    if getattr(getattr(part, "inline_data", None), "data", None):
                        with open(output_file, "wb") as output:
                            output.write(_binary_data(part.inline_data.data))
                        return {"scene_id": scene_id, "image_path": output_file,
                                "image_url": f"/api/v1/pipeline/media/{filename}", "source": settings.GEMINI_IMAGE_MODEL}
                raise ValueError("Gemini returned no image bytes")
            except Exception as error:
                raise RuntimeError(f"Gemini image generation failed: {error}") from error

        if not settings.GEMINI_MEDIA_ALLOW_FALLBACK:
            raise RuntimeError("Gemini image generation requires GEMINI_API_KEY; set GEMINI_MEDIA_ALLOW_FALLBACK=true only for offline demos")

        # High-definition visual fallback
        _create_mock_storyboard_image(
            output_path=output_file,
            scene_id=scene_id,
            header=header,
            shot_type=shot_type,
            lighting=lighting,
            prompt=image_prompt,
            scene_text=scene_text,
            color_palette=color_palette
        )

        return {
            "scene_id": scene_id,
            "image_path": output_file,
            "image_url": f"/api/v1/pipeline/media/{filename}",
            "source": "cinemagent_scenographer"
        }


class DialogueTTSTool:
    """
    Generates character dialogue audio using Gemini Flash TTS models
    (e.g., Gemini 3.1 Flash / 2.5 Flash Audio modalities) with emotional direction.
    """
    def __init__(self, output_dir: str = "artifacts/media/audio"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate_speech(
        self,
        scene_id: str,
        dialogue_id: str,
        speaker: str,
        line: str,
        emotion: str = "neutral",
        voice_profile: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generates spoken audio for a single dialogue line.
        """
        safe_speaker = "".join(c for c in speaker if c.isalnum()).lower() or "character"
        filename = f"{scene_id}_{dialogue_id}_{safe_speaker}.wav"
        output_file = str(self.output_dir / filename)
        neural_filename = f"{scene_id}_{dialogue_id}_{safe_speaker}.mp3"
        neural_output_file = str(self.output_dir / neural_filename)
        voice_profile = voice_profile or {}
        voice_name = voice_profile.get("voice_name", "Aoede")
        gender = voice_profile.get("gender", "FEMALE")

        logger.info("Flash TTS synthesizing dialogue speech", speaker=speaker, line=line[:60], emotion=emotion)

        # Determine estimated duration based on line length
        words = len(line.split())
        estimated_duration = max(1.5, round(words / 2.8, 2))

        gemini_failure: Exception | None = None
        # Use Gemini first.  A provider quota/outage must not leave a chapter
        # without any playable narration, so real local/neural voice engines
        # are attempted afterwards.
        if settings.GEMINI_API_KEY:
            try:
                from google import genai
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
            except Exception as error:
                gemini_failure = error
            else:
                try:
                    response = client.interactions.create(
                        model=settings.GEMINI_TTS_MODEL,
                        input=f"Perform exactly this line as {speaker}. Direction: {emotion}.\n\n{line}",
                        response_format={"type": "audio"}, generation_config={"speech_config": [{"voice": voice_name}]},
                    )
                    data = getattr(getattr(response, "output_audio", None), "data", None)
                    if not data:
                        raise ValueError("Gemini TTS returned no audio")
                    _write_pcm_wav(output_file, _binary_data(data))
                    return {"dialogue_id": dialogue_id, "speaker": speaker, "audio_path": output_file,
                            "audio_url": f"/api/v1/pipeline/media/{filename}", "duration_seconds": estimated_duration,
                            "source": settings.GEMINI_TTS_MODEL}
                except Exception as error:
                    gemini_failure = error
            logger.warning("Gemini TTS unavailable; generating a real fallback voice", error=str(gemini_failure))

        # Prefer a real neural voice for every writer-visible artifact.
        if await _synthesize_edge_speech(neural_output_file, line, voice_name):
            return {
                "dialogue_id": dialogue_id,
                "speaker": speaker,
                "audio_path": neural_output_file,
                "audio_url": f"/api/v1/pipeline/media/{neural_filename}",
                "duration_seconds": estimated_duration,
                "source": "edge_neural_tts"
            }

        # Use the operating system's speech engine if network TTS is not available.
        if await asyncio.to_thread(_synthesize_windows_speech, output_file, line, emotion):
            return {
                "dialogue_id": dialogue_id,
                "speaker": speaker,
                "audio_path": output_file,
                "audio_url": f"/api/v1/pipeline/media/{filename}",
                "duration_seconds": estimated_duration,
                "source": "windows_sapi_tts"
            }

        if not settings.GEMINI_MEDIA_ALLOW_FALLBACK:
            detail = f" (Gemini error: {gemini_failure})" if gemini_failure else ""
            raise RuntimeError(f"No real TTS engine is available for this worker{detail}")

        # Explicit opt-in only: never show a tone as though it were narration.
        base_freq = 150.0 if gender.upper() == "MALE" else (240.0 if gender.upper() == "FEMALE" else 190.0)
        _create_mock_wav_audio(
            output_path=output_file,
            duration_seconds=estimated_duration,
            base_freq=base_freq
        )

        return {
            "dialogue_id": dialogue_id,
            "speaker": speaker,
            "audio_path": output_file,
            "audio_url": f"/api/v1/pipeline/media/{filename}",
            "duration_seconds": estimated_duration,
            "source": "cinemagent_acoustic_synthesizer"
        }
