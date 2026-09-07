import os
import structlog
import wave
import math
import struct
from pathlib import Path
from typing import Dict, Any, Optional, List
from PIL import Image, ImageDraw, ImageFont

from src.config import settings

logger = structlog.get_logger(__name__)


def _create_mock_storyboard_image(
    output_path: str,
    scene_id: str,
    header: str,
    shot_type: str,
    lighting: str,
    prompt: str,
    color_palette: Optional[List[str]] = None
) -> str:
    """
    Generates a rich, cinematic storyboard keyframe visual using Pillow
    when live vision models are offline or for offline testing.
    """
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

    # 1. Draw cinematic gradient background
    accent_rgb = hex_to_rgb(palette[-1]) if palette else (229, 186, 115)
    for y in range(height):
        ratio = y / height
        r = int(bg_color[0] * (1 - ratio * 0.7) + accent_rgb[0] * (ratio * 0.3))
        g = int(bg_color[1] * (1 - ratio * 0.7) + accent_rgb[1] * (ratio * 0.3))
        b = int(bg_color[2] * (1 - ratio * 0.7) + accent_rgb[2] * (ratio * 0.3))
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # 2. Cinematic letterbox bars
    bar_height = 60
    draw.rectangle([(0, 0), (width, bar_height)], fill=(5, 5, 8))
    draw.rectangle([(0, height - bar_height), (width, height)], fill=(5, 5, 8))

    # 3. Inner frame & grid guides
    draw.rectangle([(40, bar_height + 20), (width - 40, height - bar_height - 20)], outline=(80, 100, 130), width=2)
    
    # Crosshair center mark
    cx, cy = width // 2, height // 2
    draw.line([(cx - 20, cy), (cx + 20, cy)], fill=(120, 140, 180), width=1)
    draw.line([(cx, cy - 20), (cx, cy + 20)], fill=(120, 140, 180), width=1)

    # 4. Text Annotations
    title_text = f"CINEMAGENT STORYBOARD — {scene_id.upper()}"
    header_text = header or "INT. CINEMATIC SCENE - NIGHT"
    shot_text = f"SHOT TYPE: {shot_type or 'Cinematic Wide'}"
    light_text = f"LIGHTING: {lighting or 'Atmospheric Moody Chiaroscuro'}"
    
    draw.text((60, 20), title_text, fill=(230, 230, 240))
    draw.text((width - 320, 20), "SCENOGRAPHER ENGINE", fill=(200, 180, 120))
    
    draw.text((60, bar_height + 40), header_text, fill=(255, 235, 170))
    draw.text((60, bar_height + 75), shot_text, fill=(180, 200, 220))
    draw.text((60, bar_height + 105), light_text, fill=(160, 180, 200))

    # Prompt box at bottom
    prompt_box_y = height - bar_height - 110
    draw.rectangle([(60, prompt_box_y), (width - 60, height - bar_height - 30)], fill=(10, 14, 20), outline=(60, 80, 110))
    
    prompt_wrapped = (prompt[:140] + "...") if len(prompt) > 140 else prompt
    draw.text((75, prompt_box_y + 15), "VISION DIRECTIVE PROMPT:", fill=(229, 186, 115))
    draw.text((75, prompt_box_y + 40), prompt_wrapped, fill=(210, 215, 225))

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
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                
                # Attempt Imagen 3 generation
                try:
                    result = client.models.generate_images(
                        model='imagen-3.0-generate-002',
                        prompt=image_prompt,
                        config={
                            'number_of_images': 1,
                            'aspect_ratio': '16:9',
                            'output_mime_type': 'image/png'
                        }
                    )
                    if result.generated_images:
                        image_bytes = result.generated_images[0].image.image_bytes
                        with open(output_file, 'wb') as f:
                            f.write(image_bytes)
                        return {
                            "scene_id": scene_id,
                            "image_path": output_file,
                            "image_url": f"/api/v1/pipeline/media/{filename}",
                            "source": "imagen-3.0-generate-002"
                        }
                except Exception as img_err:
                    logger.warn("Imagen generation failed or not permitted on key, using high-res visual storyboard generator", error=str(img_err))
            except Exception as e:
                logger.warn("Google GenAI client initialization failed", error=str(e))

        # High-definition visual fallback
        _create_mock_storyboard_image(
            output_path=output_file,
            scene_id=scene_id,
            header=header,
            shot_type=shot_type,
            lighting=lighting,
            prompt=image_prompt,
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
        voice_profile = voice_profile or {}
        voice_name = voice_profile.get("voice_name", "Aoede")
        gender = voice_profile.get("gender", "FEMALE")

        logger.info("Flash TTS synthesizing dialogue speech", speaker=speaker, line=line[:60], emotion=emotion)

        # Determine estimated duration based on line length
        words = len(line.split())
        estimated_duration = max(1.5, round(words / 2.8, 2))

        # Check if Gemini Flash Audio TTS can be used directly
        if settings.GEMINI_API_KEY:
            try:
                from google import genai
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                
                # Try generating content with audio modality if supported
                try:
                    response = client.models.generate_content(
                        model='gemini-2.0-flash',
                        contents=f"Perform this character line as voice actor for {speaker} ({emotion}): {line}",
                        config={
                            'response_modalities': ['AUDIO']
                        }
                    )
                    # If audio parts are returned
                    if response.candidates and response.candidates[0].content.parts:
                        for part in response.candidates[0].content.parts:
                            if hasattr(part, 'inline_data') and part.inline_data and part.inline_data.data:
                                with open(output_file, 'wb') as f:
                                    f.write(part.inline_data.data)
                                return {
                                    "dialogue_id": dialogue_id,
                                    "speaker": speaker,
                                    "audio_path": output_file,
                                    "audio_url": f"/api/v1/pipeline/media/{filename}",
                                    "duration_seconds": estimated_duration,
                                    "source": "gemini_flash_tts"
                                }
                except Exception as tts_err:
                    logger.warn("Flash TTS direct audio modality error, using acoustic voice synthesis fallback", error=str(tts_err))
            except Exception as e:
                logger.warn("Google GenAI client unavailable", error=str(e))

        # Acoustic Voice Synthesizer Fallback
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
