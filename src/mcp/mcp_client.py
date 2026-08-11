import asyncio
import structlog
from typing import Dict, Any, List, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from src.config import settings

logger = structlog.get_logger(__name__)

class MCPClientManager:
    """
    Manages connections to multiple MCP (Model Context Protocol) servers.
    Supports both Stdio (local process) and SSE (HTTP-based) transports.
    """
    def __init__(self):
        self.sessions: Dict[str, ClientSession] = {}
        self._exit_stack = None

    async def connect_stdio(self, name: str, command: str, args: List[str]) -> ClientSession:
        """
        Connect to a local MCP server running as a subprocess.
        """
        logger.info("Connecting to local stdio MCP server", name=name, command=command, args=args)
        try:
            server_params = StdioServerParameters(command=command, args=args)
            # Run the context manager and store session
            # Note: For simple skeletons we provide the template structure.
            # In a real environment, we'd manage the life cycles of these contexts.
            async with stdio_client(server_params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    self.sessions[name] = session
                    logger.info("Connected to stdio MCP server", name=name)
                    return session
        except Exception as e:
            logger.error("Failed to connect to stdio MCP server", name=name, error=str(e))
            raise e

    async def connect_sse(self, name: str, url: str) -> ClientSession:
        """
        Connect to a remote MCP server via SSE (HTTP).
        """
        logger.info("Connecting to remote SSE MCP server", name=name, url=url)
        try:
            async with sse_client(url) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    self.sessions[name] = session
                    logger.info("Connected to SSE MCP server", name=name)
                    return session
        except Exception as e:
            logger.error("Failed to connect to SSE MCP server", name=name, error=str(e))
            raise e

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call a tool on a connected MCP server.
        """
        session = self.sessions.get(server_name)
        if not session:
            logger.error("Attempted to call tool on disconnected MCP server", server_name=server_name)
            raise ValueError(f"No active session for MCP server: {server_name}")
        
        logger.info("Calling MCP tool", server_name=server_name, tool=tool_name, args=arguments)
        try:
            result = await session.call_tool(tool_name, arguments)
            return result
        except Exception as e:
            logger.error("Failed to execute MCP tool", server_name=server_name, tool=tool_name, error=str(e))
            raise e

    async def list_tools(self, server_name: str) -> List[Any]:
        """
        List tools available on a connected MCP server.
        """
        session = self.sessions.get(server_name)
        if not session:
            return []
        try:
            tools_response = await session.list_tools()
            return tools_response.tools
        except Exception as e:
            logger.error("Failed to list tools", server_name=server_name, error=str(e))
            return []

    async def run_search(self, query: str) -> str:
        """
        A helper method specifically targeting the Search MCP.
        If configured, queries the Search MCP server to fetch search results.
        """
        if not settings.SEARCH_MCP_URL:
            logger.warn("Search MCP URL is not configured. Skipping search.")
            return "Search MCP not configured."

        # In production, we'd establish the session on startup.
        # This is a fallback mock/placeholder showing how tool calls are structured.
        logger.info("Running parallel web search via Search MCP", query=query)
        try:
            # We mock the return if not connected, showing the interface:
            if "search_mcp" not in self.sessions:
                # Stub output simulating connection fallback
                return f"[Mock Search Results for: '{query}'] Found 3 records. 1. ClickHouse documentation. 2. Google Cloud Run setup. 3. GraphRAG details."
            
            # Assuming search_mcp has a tool called "web_search"
            result = await self.call_tool("search_mcp", "web_search", {"query": query})
            return str(result)
        except Exception as e:
            logger.error("Search MCP query execution failed", error=str(e))
            return f"Error executing search: {str(e)}"
            
    async def close_all(self):
        """Clean up sessions on shutdown."""
        self.sessions.clear()
        logger.info("All MCP sessions cleared.")
