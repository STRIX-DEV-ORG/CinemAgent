import clickhouse_connect
from clickhouse_connect.driver.client import Client
from pathlib import Path
from typing import Iterator
import structlog
from src.config import settings

logger = structlog.get_logger(__name__)

_client: Client = None
MIGRATIONS_DIR = Path(__file__).parent / "migrations"

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


def get_clickhouse_root_client() -> Client:
    """Return a ClickHouse client connected without selecting an application database."""
    return clickhouse_connect.get_client(
        host=settings.CLICKHOUSE_HOST,
        port=settings.CLICKHOUSE_PORT,
        username=settings.CLICKHOUSE_USER,
        password=settings.CLICKHOUSE_PASSWORD,
        secure=settings.CLICKHOUSE_SECURE,
    )


def _split_sql_statements(sql: str) -> Iterator[str]:
    """Yield semicolon-terminated SQL statements while preserving quoted values."""
    statement: list[str] = []
    quote: str | None = None
    escaped = False

    for character in sql:
        statement.append(character)

        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
        elif character in {"'", '"', '`'}:
            quote = character
        elif character == ";":
            query = "".join(statement).strip()
            if query:
                yield query
            statement = []

    query = "".join(statement).strip()
    if query:
        yield query


def execute_sql_file(filename: str, client: Client | None = None) -> None:
    """Execute every statement in a ClickHouse SQL migration file.

    ClickHouse's ``command`` method executes a single statement, so migration
    files are split before execution. When no client is supplied, the helper
    connects without an application database selected; this supports migration
    files that choose their database with ``USE``.
    """
    migration_path = MIGRATIONS_DIR / filename
    sql = migration_path.read_text(encoding="utf-8")
    migration_client = client if client is not None else get_clickhouse_root_client()

    logger.info("Executing ClickHouse SQL migration", migration=filename)
    for statement in _split_sql_statements(sql):
        migration_client.command(statement)
    logger.info("ClickHouse SQL migration completed", migration=filename)


def create_schemas(client: Client | None = None) -> None:
    """Create the ClickHouse narrative-graph tables from the schema migration."""
    execute_sql_file("create_schemas.sql", client)


def drop_schemas(client: Client | None = None) -> None:
    """Drop the ClickHouse narrative-graph tables from the schema migration."""
    execute_sql_file("drop_schemas.sql", client)


def execute_create_schemas(client: Client | None = None) -> None:
    """Execute the ClickHouse create-schema migration."""
    create_schemas(client)


def execute_drop_schemas(client: Client | None = None) -> None:
    """Execute the ClickHouse drop-schema migration."""
    drop_schemas(client)


def init_db() -> None:
    """
    Run initial DDL setup on ClickHouse.
    Creates default database and tables if they do not exist.
    """
    logger.info("Starting database schema initialization...")
    try:
        # First connect without specifying database to create it if it doesn't exist
        root_client = get_clickhouse_root_client()
        
        # Create database
        root_client.command(f"CREATE DATABASE IF NOT EXISTS {settings.CLICKHOUSE_DATABASE}")
        logger.info(f"Database '{settings.CLICKHOUSE_DATABASE}' ready.")

        # Run the narrative-graph DDL added in the SQL migrations. The migration
        # selects its target database, so execute it with the root client.
        create_schemas(root_client)
        
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
