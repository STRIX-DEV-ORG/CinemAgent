import unittest
import json
from unittest.mock import patch, MagicMock, AsyncMock

from src.config import settings
from src.agent.tools.parallel_search import parallel_web_search, search_parallel_api, get_parallel_client, get_async_parallel_client
from src.agent.searcher_agent import searcher_investigator_executor, searcher_investigator_agent
from src.agent.models import InvestigatorRequest


class TestParallelSearch(unittest.IsolatedAsyncioTestCase):

    def test_searcher_investigator_agent_tool_registration(self):
        """Ensure searcher_investigator_agent has search_parallel_api registered in tools."""
        tool_names = [getattr(t, "__name__", str(t)) for t in searcher_investigator_agent.tools]
        self.assertIn("search_parallel_api", tool_names)

    async def test_missing_api_key_raises_value_error(self):
        """Test that missing PARALLEL_API_KEY immediately raises ValueError without fallbacks."""
        with patch.object(settings, "PARALLEL_API_KEY", ""):
            with patch.dict("os.environ", {}, clear=True):
                with self.assertRaises(ValueError):
                    await parallel_web_search("Did samurai use flintlock pistols in 1300?")

    def test_missing_api_key_sync_tool_raises_value_error(self):
        """Test that synchronous tool raises ValueError when API key is missing."""
        with patch.object(settings, "PARALLEL_API_KEY", ""):
            with patch.dict("os.environ", {}, clear=True):
                with self.assertRaises(ValueError):
                    search_parallel_api("Gothic architecture in 12th century France")

    async def test_parallel_client_task_run_create(self):
        """Test Parallel client task_run.create SDK pattern."""
        mock_task_run = MagicMock()
        mock_task_run.interaction_id = "interact_abc_12345"

        mock_client = MagicMock()
        mock_client.task_run.create = AsyncMock(return_value=mock_task_run)

        with patch("src.agent.tools.parallel_search.get_async_parallel_client", return_value=mock_client), \
             patch.object(settings, "PARALLEL_API_KEY", "test_key_123"):
            
            res = await parallel_web_search(
                query="What was the GDP of France in 2023?",
                processor="base"
            )
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["search_id"], "interact_abc_12345")
            self.assertIn("interact_abc_12345", res["summary"])

    def test_search_parallel_api_sync_tool(self):
        """Test synchronous search_parallel_api tool wrapper."""
        mock_task_run = MagicMock()
        mock_task_run.interaction_id = "sync_interact_999"

        mock_client = MagicMock()
        mock_client.task_run.create.return_value = mock_task_run

        with patch("src.agent.tools.parallel_search.get_parallel_client", return_value=mock_client), \
             patch.object(settings, "PARALLEL_API_KEY", "test_key_123"):
            
            res_json_str = search_parallel_api("Gothic architecture in 12th century France")
            data = json.loads(res_json_str)
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["interaction_id"], "sync_interact_999")

    async def test_executor_with_parallel_search(self):
        """Test searcher_investigator_executor end-to-end execution with Parallel Search."""
        mock_task_run = MagicMock()
        mock_task_run.interaction_id = "inv_interact_777"

        mock_client = MagicMock()
        mock_client.task_run.create = AsyncMock(return_value=mock_task_run)

        with patch("src.agent.tools.parallel_search.get_async_parallel_client", return_value=mock_client), \
             patch.object(settings, "PARALLEL_API_KEY", "test_key_123"):
            
            req = InvestigatorRequest(
                query="A Venetian guard aims a flintlock pistol in 1350 CE.",
                era_context="14th Century Venice (1350 CE)",
                genre="historical fiction"
            )
            resp = await searcher_investigator_executor.execute(req)
            self.assertEqual(resp.verdict, "ANACHRONISTIC")
            self.assertGreater(len(resp.search_sources), 0)
            self.assertEqual(resp.metadata["parallel_search_id"], "inv_interact_777")


if __name__ == "__main__":
    unittest.main()
