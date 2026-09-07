import os
import asyncio
import unittest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from src.main import app
from src.agent.models import ScreenplayPipelineRequest, PipelineProgressStatus
from src.agent.tools.genmedia_tools import ScenographerTool, DialogueTTSTool
from src.agent.tools.pdf_generator import ScreenplayPDFGenerator
from src.agent.orchestrator import AgentOrchestrator, task_progress_store


class TestGenMediaPipeline(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.orchestrator = AgentOrchestrator()

    def test_scenographer_tool_image_generation(self):
        """Test that ScenographerTool creates a valid PNG image file."""
        tool = ScenographerTool(output_dir="artifacts/media/images")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(
            tool.generate_scene_image(
                scene_id="test_scene_01",
                image_prompt="INT. High-tech command deck, dramatic neon blue lighting",
                header="INT. COMMAND DECK - NIGHT",
                shot_type="Extreme Wide Shot",
                lighting="Neon Cyberpunk Blue"
            )
        )
        
        self.assertIn("image_path", result)
        self.assertTrue(os.path.exists(result["image_path"]))
        self.assertTrue(result["image_path"].endswith(".png"))

    def test_dialogue_tts_tool_audio_generation(self):
        """Test that DialogueTTSTool creates a valid WAV audio file."""
        tool = DialogueTTSTool(output_dir="artifacts/media/audio")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(
            tool.generate_speech(
                scene_id="test_scene_01",
                dialogue_id="dial_01",
                speaker="Elena",
                line="We cannot abort the sequence now. Look at the telemetry.",
                emotion="intense urgency",
                voice_profile={"voice_name": "Aoede", "gender": "FEMALE"}
            )
        )
        
        self.assertIn("audio_path", result)
        self.assertTrue(os.path.exists(result["audio_path"]))
        self.assertTrue(result["audio_path"].endswith(".wav"))
        self.assertGreater(result.get("duration_seconds", 0), 0)

    def test_pdf_screenplay_generation(self):
        """Test that ScreenplayPDFGenerator produces a valid PDF stamped with PyPDF."""
        pdf_gen = ScreenplayPDFGenerator(output_dir="artifacts/pdf")
        
        # Mock media artifacts
        media_artifacts = [{
            "scene_id": "scene_plan_01",
            "image_path": "artifacts/media/images/test_scene_01_storyboard.png",
            "dialogues": [{
                "dialogue_id": "dial_01",
                "speaker": "Elena",
                "parenthetical": "whispering fiercely",
                "line": "The cipher is decoding itself.",
                "duration_seconds": 2.5,
                "voice_profile": {"voice_name": "Aoede"}
            }]
        }]
        
        pdf_path = pdf_gen.generate_screenplay_pdf(
            task_id="test_pdf_task",
            title="The Quantum Threshold",
            story_request={"genre": "sci-fi", "tone": "suspenseful"},
            narrative_outline={"narrativeOutline": {"title": "The Quantum Threshold"}},
            scene_plans_data={"scenePlans": [{"id": "scene_plan_01", "settingId": "loc_laboratory"}]},
            scenes_generation={"scene_plan_01": {"results": {"style_agent": {"polishedProse": "Sparks danced across the mainframe."}}}},
            media_artifacts=media_artifacts
        )
        
        self.assertTrue(os.path.exists(pdf_path))
        self.assertTrue(pdf_path.endswith(".pdf"))
        self.assertGreater(os.path.getsize(pdf_path), 1000)

    def test_orchestrator_full_screenplay_pipeline(self):
        """Test end-to-end execution of orchestrator.execute_screenplay_pipeline with progress tracking."""
        req = ScreenplayPipelineRequest(
            story_prompt="Elena Vance discovers the hidden stellar core in the observatory.",
            genre="sci-fi mystery",
            tone="suspenseful",
            enable_images=True,
            enable_tts=True,
            enable_pdf=True
        )
        
        progress_history = []
        async def on_progress(status: PipelineProgressStatus):
            progress_history.append((status.status_value, status.current_agent, status.status_message))
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        task_id = "test_e2e_task_123"
        result = loop.run_until_complete(
            self.orchestrator.execute_screenplay_pipeline(
                task_id=task_id,
                request=req,
                progress_callback=on_progress
            )
        )
        
        self.assertEqual(result["task_id"], task_id)
        self.assertIn("narrative_outline", result)
        self.assertIn("scene_plans", result)
        self.assertIn("pdf_path", result)
        self.assertTrue(os.path.exists(result["pdf_path"]))
        
        # Verify status reached 100%
        final_status = task_progress_store.get(task_id)
        self.assertIsNotNone(final_status)
        self.assertEqual(final_status.status_value, 100)
        self.assertTrue(final_status.is_completed)
        self.assertGreater(len(progress_history), 5)

    def test_api_pipeline_endpoints(self):
        """Test FastAPI /api/v1/pipeline endpoints."""
        payload = {
            "story_prompt": "Marcus attempts to lock down the royal archives.",
            "genre": "political thriller",
            "tone": "tense",
            "enable_images": True,
            "enable_tts": True,
            "enable_pdf": True
        }
        
        # 1. Trigger generate endpoint
        post_res = self.client.post("/api/v1/pipeline/generate", json=payload)
        self.assertEqual(post_res.status_code, 200)
        data = post_res.json()
        self.assertIn("task_id", data)
        self.assertEqual(data["status_value"], 0)
        task_id = data["task_id"]
        
        # 2. Query status endpoint
        status_res = self.client.get(f"/api/v1/pipeline/status/{task_id}")
        self.assertEqual(status_res.status_code, 200)
        status_data = status_res.json()
        self.assertEqual(status_data["task_id"], task_id)
        self.assertIn("status_value", status_data)

    def test_standalone_scenographer_endpoint(self):
        """Test POST /api/v1/agents/scenographer for single-click chapter image generation."""
        payload = {
            "chapter_text": "INT. ROYAL OBSERVATORY - NIGHT. Elena stares into the spinning astrolabe as violet sparks illuminate the marble dome.",
            "chapter_title": "Chapter 1: Celestial Revelation",
            "segment_ids": ["seg_01_01", "seg_01_02"],
            "genre": "sci-fi mystery",
            "tone": "mysterious violet neon"
        }
        res = self.client.post("/api/v1/agents/scenographer", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("scene_id", data)
        self.assertIn("visual_concept", data)
        self.assertIn("image_path", data)
        self.assertTrue(os.path.exists(data["image_path"]))

    def test_standalone_dialoger_endpoint(self):
        """Test POST /api/v1/agents/dialoger for single-click chapter speech extraction & audio synthesis."""
        payload = {
            "chapter_text": 'Elena glanced at Marcus. "We found the resonance anomaly in sector four." Marcus stepped forward. "Keep your voice down, Elena."',
            "chapter_title": "Chapter 2: The Confrontation",
            "segment_ids": ["seg_02_01"],
            "character_hints": {"Elena": "Aoede", "Marcus": "Fenrir"},
            "emotion_hint": "urgent whisper"
        }
        res = self.client.post("/api/v1/agents/dialoger", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("dialogues", data)
        self.assertGreater(len(data["dialogues"]), 0)
        self.assertGreater(data["total_audio_duration_seconds"], 0)
        for dial in data["dialogues"]:
            self.assertIn("audio_path", dial)
            self.assertTrue(os.path.exists(dial["audio_path"]))

    @patch("src.agent.searcher_agent.parallel_web_search", new_callable=AsyncMock)
    def test_standalone_searcher_investigator_endpoint(self, mock_search):
        """Test POST /api/v1/agents/searcher for historical fact checking and anachronism detection."""
        mock_search.return_value = {
            "status": "success",
            "search_id": "test_search_id_001",
            "results": [
                {
                    "title": "Historical Firearms Archive",
                    "url": "https://parallel.ai/firearms-archive",
                    "type": "Parallel Web Search",
                    "excerpts": ["Flintlock mechanisms were developed circa 1610."]
                }
            ],
            "summary": "Parallel Search Results: Flintlock mechanisms were developed in the 17th century."
        }
        payload = {
            "query": "A Venetian guard aims a flintlock pistol in 1350 CE.",
            "era_context": "14th Century Venice (1350 CE)",
            "genre": "historical fiction"
        }
        res = self.client.post("/api/v1/agents/searcher", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("verdict", data)
        self.assertIn("historical_summary", data)
        self.assertIn("detected_anachronisms", data)
        self.assertIn("recommendations_for_writers", data)
        self.assertEqual(data["verdict"], "ANACHRONISTIC")
        self.assertEqual(len(data["search_sources"]), 1)
        self.assertEqual(data["search_sources"][0]["type"], "Parallel Web Search")


if __name__ == "__main__":
    unittest.main()

