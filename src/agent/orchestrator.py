import asyncio
import time
import structlog
from jinja2 import Template
from typing import Dict, Any

from src.config import settings
from src.rag.retriever import Retriever
from src.mcp.mcp_client import MCPClientManager
from src.agent.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

logger = structlog.get_logger(__name__)

class AgentOrchestrator:
    """
    Main agent runtime. Orchestrates RAG context gathering, 
    external MCP client tools execution (in parallel), and LLM generation.
    """
    def __init__(self):
        self.retriever = Retriever()
        self.mcp_manager = MCPClientManager()
        
        # Determine model capabilities
        self.has_llm = bool(settings.GEMINI_API_KEY or settings.OPENAI_API_KEY)
        if not self.has_llm:
            logger.warn("No API Keys configured for Gemini or OpenAI. The agent will return mock responses.")

    async def generate_response(self, prompt: str) -> str:
        """
        Send the generated prompt to the LLM.
        """
        if not self.has_llm:
            return "[Mock Agent Response] I received your prompt, but no API keys are configured. Connect ClickHouse and add GEMINI_API_KEY to test LLM generation."

        try:
            if settings.GEMINI_API_KEY:
                # Call Gemini SDK
                from google import genai
                client = genai.Client(api_key=settings.GEMINI_API_KEY)
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config={
                        'system_instruction': SYSTEM_PROMPT
                    }
                )
                return response.text
                

        except Exception as e:
            logger.error("LLM Generation failed", error=str(e))
            return f"Failed to generate response: {str(e)}"

    async def execute_pipeline(self, query: str) -> Dict[str, Any]:
        """
        Runs the RAG retriever and Search MCP tool execution in parallel.
        Combines contexts and queries the LLM.
        """
        start_time = time.perf_counter()
        logger.info("Executing Agent loop", query=query)

        # Execute ClickHouse RAG + MCP Search in PARALLEL
        retrieval_task = asyncio.to_thread(self.retriever.retrieve_context, query)
        search_task = self.mcp_manager.run_search(query)

        logger.info("Awaiting parallel retrieval and web search...")
        retrieval_res, search_res = await asyncio.gather(retrieval_task, search_task)
        logger.info("Parallel processes completed")

        # Render User Prompt using Jinja2
        template = Template(USER_PROMPT_TEMPLATE)
        rendered_prompt = template.render(
            context=retrieval_res["combined_context"],
            search_results=search_res,
            query=query
        )

        # Generate output from model
        response_text = await self.generate_response(rendered_prompt)
        
        elapsed = time.perf_counter() - start_time
        logger.info("Agent execution completed", duration_seconds=round(elapsed, 3))

        return {
            "query": query,
            "response": response_text,
            "metadata": {
                "execution_time_seconds": round(elapsed, 3),
                "retrieved_nodes_count": len(retrieval_res.get("graph_entities", [])),
                "vector_chunks_retrieved": len(retrieval_res.get("vector_hits", [])),
                "search_mcp_queried": bool(settings.SEARCH_MCP_URL)
            }
        }
