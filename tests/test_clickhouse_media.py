import base64
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4
from fastapi.testclient import TestClient

from src.main import app
from src.db.clickhouse_client import (
    save_segment_media,
    get_segment_media,
    get_segment_all_media,
)


class Result:
    def __init__(self, columns, rows):
        self.column_names = columns
        self.result_rows = rows


class TestClickHouseMedia(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_save_segment_media_insert_new(self):
        """Test inserting new source_segment with media when record does not exist."""
        mock_ch = Mock()
        mock_ch.query.return_value = Result(["id"], [])  # Not existing

        fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR..."
        fake_wav = b"RIFF....WAVEfmt ...."

        segment_id = str(uuid4())
        success = save_segment_media(
            segment_id=segment_id,
            image_data=fake_png,
            image_mime="image/png",
            audio_data=fake_wav,
            audio_mime="audio/wav",
            metadata={"prompt": "Scene keyframe concept"},
            client=mock_ch,
        )

        self.assertTrue(success)
        self.assertEqual(mock_ch.insert.call_count, 1)
        table_name, rows = mock_ch.insert.call_args[0]
        self.assertEqual(table_name, "source_segment")
        self.assertEqual(rows[0][0], segment_id)
        # Check base64 encoded media strings
        self.assertEqual(rows[0][6], base64.b64encode(fake_png).decode("utf-8"))
        self.assertEqual(rows[0][7], "image/png")
        self.assertEqual(rows[0][8], base64.b64encode(fake_wav).decode("utf-8"))
        self.assertEqual(rows[0][9], "audio/wav")

    def test_save_segment_media_update_existing(self):
        """Test updating existing source_segment with new media."""
        mock_ch = Mock()
        segment_id = str(uuid4())
        mock_ch.query.return_value = Result(["id"], [[segment_id]])  # Existing

        fake_png = b"\x89PNG_UPDATED_KEYFRAME"

        success = save_segment_media(
            segment_id=segment_id,
            image_data=fake_png,
            image_mime="image/png",
            client=mock_ch,
        )

        self.assertTrue(success)
        self.assertEqual(mock_ch.command.call_count, 1)
        cmd = mock_ch.command.call_args[0][0]
        self.assertIn("ALTER TABLE source_segment UPDATE", cmd)
        self.assertIn("image_data = %(image_data)s", cmd)

    def test_get_segment_media(self):
        """Test retrieving raw bytes and MIME type from ClickHouse."""
        mock_ch = Mock()
        segment_id = str(uuid4())
        fake_png = b"\x89PNG_TEST_BINARY_DATA"
        fake_png_b64 = base64.b64encode(fake_png).decode("utf-8")

        mock_ch.query.return_value = Result(["image_data", "image_mime"], [[fake_png_b64, "image/png"]])

        data, mime = get_segment_media(segment_id, media_type="image", client=mock_ch)
        self.assertEqual(data, fake_png)
        self.assertEqual(mime, "image/png")

    def test_get_segment_all_media_summary(self):
        """Test retrieving all media info metadata for a segment."""
        mock_ch = Mock()
        segment_id = str(uuid4())
        mock_ch.query.return_value = Result(
            ["id", "graph_id", "chapter", "sequence", "has_image", "image_mime", "image_size", "has_audio", "audio_mime", "audio_size", "media_metadata"],
            [[segment_id, None, 1, 1, 1, "image/png", 1024, 1, "audio/wav", 2048, {"speaker": "Elena"}]]
        )

        info = get_segment_all_media(segment_id, client=mock_ch)
        self.assertIsNotNone(info)
        self.assertEqual(info["segment_id"], segment_id)
        self.assertTrue(info["has_image"])
        self.assertEqual(info["image_size_bytes"], 1024)
        self.assertTrue(info["has_audio"])
        self.assertEqual(info["audio_size_bytes"], 2048)

    @patch("src.api.media.get_segment_media")
    def test_download_segment_image_endpoint(self, mock_get_media):
        """Test GET /api/v1/media/segment/{segment_id}/image download endpoint."""
        fake_bytes = b"\x89PNG_ENDPOINT_DOWNLOAD_BYTES"
        mock_get_media.return_value = (fake_bytes, "image/png")

        segment_id = str(uuid4())
        res = self.client.get(f"/api/v1/media/segment/{segment_id}/image?download=true")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.content, fake_bytes)
        self.assertEqual(res.headers["content-type"], "image/png")
        self.assertIn("Content-Disposition", res.headers)
        self.assertIn(f"segment_{segment_id}.png", res.headers["Content-Disposition"])

    @patch("src.api.media.get_segment_media")
    def test_download_segment_audio_endpoint(self, mock_get_media):
        """Test GET /api/v1/media/segment/{segment_id}/audio download endpoint."""
        fake_wav_bytes = b"RIFF_AUDIO_ENDPOINT_DOWNLOAD_BYTES"
        mock_get_media.return_value = (fake_wav_bytes, "audio/wav")

        segment_id = str(uuid4())
        res = self.client.get(f"/api/v1/media/segment/{segment_id}/audio?download=true")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.content, fake_wav_bytes)
        self.assertEqual(res.headers["content-type"], "audio/wav")
        self.assertIn("Content-Disposition", res.headers)
        self.assertIn(f"segment_{segment_id}.wav", res.headers["Content-Disposition"])

    @patch("src.api.media.get_segment_all_media")
    def test_get_segment_media_info_endpoint(self, mock_get_info):
        """Test GET /api/v1/media/segment/{segment_id} info endpoint."""
        segment_id = str(uuid4())
        mock_get_info.return_value = {
            "segment_id": segment_id,
            "graph_id": None,
            "chapter": 1,
            "sequence": 1,
            "has_image": True,
            "image_mime": "image/png",
            "image_size_bytes": 512,
            "has_audio": True,
            "audio_mime": "audio/wav",
            "audio_size_bytes": 1024,
            "media_metadata": {"scene": "command_deck"}
        }

        res = self.client.get(f"/api/v1/media/segment/{segment_id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["segment_id"], segment_id)
        self.assertTrue(data["has_image"])
        self.assertEqual(data["image_download_url"], f"/api/v1/media/segment/{segment_id}/image")
        self.assertTrue(data["has_audio"])
        self.assertEqual(data["audio_download_url"], f"/api/v1/media/segment/{segment_id}/audio")


if __name__ == "__main__":
    unittest.main()
