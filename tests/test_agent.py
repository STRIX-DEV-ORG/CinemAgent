import unittest
from fastapi.testclient import TestClient

from src.config import settings
from src.rag.embedder import Embedder
from src.rag.retriever import Retriever
from src.main import app


class TestCinemAgent(unittest.TestCase):
    
    def test_settings_load(self):
        """Test configuration defaults load correctly."""
        self.assertIsNotNone(settings.PORT)
        self.assertEqual(settings.CLICKHOUSE_DATABASE, "cinemagent")

    def test_embedder_mock(self):
        """Test mock embedder return size."""
        embedder = Embedder()
        vector = embedder.get_embedding("The Matrix Resurrections")
        self.assertEqual(len(vector), 768)

    def test_entity_extraction(self):
        """Test basic entity extraction tokenizing rules."""
        retriever = Retriever()
        entities = retriever.extract_entities_stub("Who directed the movie Interstellar and starring Matthew McConaughey?")
        # Capitalized/large words like Interstellar, Matthew, McConaughey should be identified
        self.assertIn("interstellar", entities)
        self.assertIn("matthew", entities)

    def test_health_endpoint_fallback(self):
        """Test health endpoint responds (might show degraded if ClickHouse isn't local, which is fine)."""
        with TestClient(app) as client:
            response = client.get("/health")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIn("status", data)
            self.assertIn("database", data)


if __name__ == "__main__":
    unittest.main()
