import unittest
from typing import Any
from fastapi.testclient import TestClient
from google.adk import Context, Workflow
from google.adk.workflow import node

from src.config import settings
from src.rag.embedder import Embedder
from src.rag.retriever import Retriever
from src.main import app


@node(name="hello_node")
def my_node(node_input: Any):
    return "Hello World"


@node(rerun_on_resume=True)
async def my_workflow(ctx: Context, node_input: str) -> str:
    # run_node executes a node and returns its output
    result = await ctx.run_node(my_node, node_input="hello")
    return result


root_agent = Workflow(
    name="root_agent",
    edges=[("START", my_workflow)],
)


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
        self.assertIn("interstellar", entities)
        self.assertIn("matthew", entities)

    def test_health_endpoint_fallback(self):
        """Test health endpoint responds."""
        with TestClient(app) as client:
            response = client.get("/health")
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIn("status", data)
            self.assertIn("database", data)

    def test_workflow_definition(self):
        """Test ADK workflow structure initialization."""
        self.assertEqual(root_agent.name, "root_agent")


if __name__ == "__main__":
    unittest.main()

