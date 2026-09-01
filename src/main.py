import uvicorn
import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager

from src.config import settings
from src.db.clickhouse_client import init_db, get_clickhouse_client
from src.agent.orchestrator import AgentOrchestrator
from src.api.narrative_graph import router as narrative_graph_router

# Setup structured logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger()

# Orchestrator lazy/startup initialization
orchestrator: AgentOrchestrator = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    global orchestrator
    logger.info("Starting up CinemAgent web application...")
    
    # 1. Initialize ClickHouse schemas
    try:
        init_db()
    except Exception as e:
        logger.error("ClickHouse startup initialization failed", error=str(e))
        # We don't crash, but log it; database might connect later
        
    # 2. Instantiate Orchestrator
    orchestrator = AgentOrchestrator()
    logger.info("Agent orchestrator initialized.")
    
    yield
    
    # Shutdown actions
    logger.info("Shutting down CinemAgent...")
    if orchestrator and orchestrator.mcp_manager:
        await orchestrator.mcp_manager.close_all()

app = FastAPI(
    title="CinemAgent API",
    description="FastAPI endpoint for CinemAgent's parallel RAG and Knowledge Graph search agent.",
    version="0.1.0",
    lifespan=lifespan
)
app.include_router(narrative_graph_router)


class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    query: str
    response: str
    metadata: dict


@app.get("/health")
def health_check():
    """
    Checks connection to ClickHouse database.
    """
    try:
        client = get_clickhouse_client()
        is_alive = client.ping()
        if not is_alive:
            raise HTTPException(status_code=503, detail="ClickHouse did not ping successfully")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return {"status": "degraded", "database": "disconnected", "error": str(e)}


@app.post("/query", response_model=QueryResponse)
async def query_agent(request: QueryRequest):
    """
    Post a search or analytics query to CinemAgent.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query string cannot be empty")
        
    try:
        result = await orchestrator.execute_pipeline(request.query)
        return QueryResponse(
            query=result["query"],
            response=result["response"],
            metadata=result["metadata"]
        )
    except Exception as e:
        logger.exception("Error executing user query", query=request.query)
        raise HTTPException(status_code=500, detail=f"Internal agent query error: {str(e)}")


if __name__ == "__main__":
    # Start web application on port specified in settings
    uvicorn.run("main:app", host="0.0.0.0", port=settings.PORT, reload=settings.DEBUG)
