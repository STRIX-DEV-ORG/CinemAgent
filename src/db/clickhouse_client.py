import clickhouse_connect
from clickhouse_connect.driver.client import Client
import structlog
from src.config import settings

logger = structlog.get_logger(__name__)

_client: Client = None

def get_clickhouse_client() -> Client:
    """
    Get or create a ClickHouse client singleton.
    """
    global _client
    if _client is None:
        try:
            logger.info("Initializing ClickHouse client connection", 
                        host=settings.CLICKHOUSE_HOST, 
                        port=settings.CLICKHOUSE_PORT,
                        database=settings.CLICKHOUSE_DATABASE)
            
            _client = clickhouse_connect.get_client(
                host=settings.CLICKHOUSE_HOST,
                port=settings.CLICKHOUSE_PORT,
                username=settings.CLICKHOUSE_USER,
                password=settings.CLICKHOUSE_PASSWORD,
                database=settings.CLICKHOUSE_DATABASE,
                secure=settings.CLICKHOUSE_SECURE,
                connect_timeout=10,
                send_receive_timeout=30
            )
            logger.info("ClickHouse client connected successfully")
        except Exception as e:
            logger.error("Failed to connect to ClickHouse database", error=str(e))
            raise e
    return _client


def init_db() -> None:
    """
    Run initial DDL setup on ClickHouse.
    Creates default database and tables if they do not exist.
    """
    logger.info("Starting database schema initialization...")
    try:
        # First connect without specifying database to create it if it doesn't exist
        root_client = clickhouse_connect.get_client(
            host=settings.CLICKHOUSE_HOST,
            port=settings.CLICKHOUSE_PORT,
            username=settings.CLICKHOUSE_USER,
            password=settings.CLICKHOUSE_PASSWORD,
            secure=settings.CLICKHOUSE_SECURE
        )
        
        # Create database
        root_client.command(f"CREATE DATABASE IF NOT EXISTS {settings.CLICKHOUSE_DATABASE}")
        logger.info(f"Database '{settings.CLICKHOUSE_DATABASE}' ready.")
        
        # Now connect to specific database to build tables
        client = get_clickhouse_client()
        
        # Create Vector Embeddings Table
        client.command("""
        CREATE TABLE IF NOT EXISTS document_chunks (
            id UUID DEFAULT generateUUIDv4(),
            document_id String,
            chunk_index UInt32,
            content String,
            embedding Array(Float32),
            metadata Map(String, String),
            created_at DateTime DEFAULT now()
        ) ENGINE = MergeTree()
        ORDER BY (document_id, chunk_index)
        """)
        logger.info("Table 'document_chunks' initialized.")
        
        # Create Knowledge Graph Nodes Table
        client.command("""
        CREATE TABLE IF NOT EXISTS kg_nodes (
            id String,
            name String,
            type String,
            description String,
            embedding Array(Float32),
            properties Map(String, String),
            updated_at DateTime DEFAULT now()
        ) ENGINE = MergeTree()
        ORDER BY id
        """)
        logger.info("Table 'kg_nodes' initialized.")
        
        # Create Knowledge Graph Edges Table
        client.command("""
        CREATE TABLE IF NOT EXISTS kg_edges (
            id UUID DEFAULT generateUUIDv4(),
            source_id String,
            target_id String,
            relation String,
            description String,
            weight Float32 DEFAULT 1.0,
            properties Map(String, String),
            updated_at DateTime DEFAULT now()
        ) ENGINE = MergeTree()
        ORDER BY (source_id, relation)
        """)
        logger.info("Table 'kg_edges' initialized.")

    except Exception as e:
        logger.error("Database schema initialization failed", error=str(e))
        raise e
