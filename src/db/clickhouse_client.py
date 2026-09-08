from opentelemetry.metrics import obj
import clickhouse_connect
from clickhouse_connect.driver.client import Client
from pathlib import Path
from typing import Any, Iterator
import structlog
from src.config import settings

logger = structlog.get_logger(__name__)

_client: Client = None
_client_failed: bool = False
MIGRATIONS_DIR = Path(__file__).parent / "migrations"

def get_clickhouse_client() -> Client:
    """
    Get or create a ClickHouse client singleton.
    """
    global _client, _client_failed
    if _client_failed:
        raise ConnectionError("ClickHouse database is offline/unreachable.")

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
                autogenerate_session_id=False,
                connect_timeout=2,
                send_receive_timeout=5
            )
            logger.info("ClickHouse client connected successfully")
        except Exception as e:
            _client_failed = True
            logger.error("Failed to connect to ClickHouse database", error=str(e))
            raise e
    return _client


def _split_sql_statements(sql: str) -> Iterator[str]:
    """Yield semicolon-terminated SQL statements while preserving quoted values."""
    # Migration comments may contain semicolons. Exclude full-line comments
    # before splitting so they are never sent to ClickHouse as empty queries.
    sql = "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))
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
    uses the configured application database.
    """
    migration_path = MIGRATIONS_DIR / filename
    sql = migration_path.read_text(encoding="utf-8")
    migration_client = client if client is not None else get_clickhouse_client()

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
        root_client = get_clickhouse_client()
        
        # Create database
        root_client.command(f"CREATE DATABASE IF NOT EXISTS {settings.CLICKHOUSE_DATABASE}")
        logger.info(f"Database '{settings.CLICKHOUSE_DATABASE}' ready.")

        # Run narrative-graph DDL in the configured application database.
        create_schemas(root_client)
        
        # Create Vector Embeddings Table
        root_client.command("""
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
        root_client.command("""
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
        root_client.command("""
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


# -----------------------------------------------------------------------------
# Media (Image & Audio) Storage Functions for Source Segments
# -----------------------------------------------------------------------------

def save_segment_media(
    segment_id: str,
    image_data: bytes | str | None = None,
    image_mime: str = "image/png",
    audio_data: bytes | str | None = None,
    audio_mime: str = "audio/wav",
    metadata: dict[str, str] | None = None,
    client: Client | None = None,
) -> bool:
    """
    Saves or updates media (image bitmaps and audio) for a specific source_segment.
    Accepts raw binary bytes or base64-encoded strings.
    """
    import base64
    ch_client = client if client is not None else get_clickhouse_client()

    image_b64 = ""
    if isinstance(image_data, bytes):
        image_b64 = base64.b64encode(image_data).decode("utf-8")
    elif isinstance(image_data, str):
        image_b64 = image_data

    audio_b64 = ""
    if isinstance(audio_data, bytes):
        audio_b64 = base64.b64encode(audio_data).decode("utf-8")
    elif isinstance(audio_data, str):
        audio_b64 = audio_data

    meta = metadata or {}
    logger.info(
        "Saving media for source_segment",
        segment_id=segment_id,
        has_image=bool(image_b64),
        has_audio=bool(audio_b64)
    )

    try:
        existing = ch_client.query(
            "SELECT id FROM source_segment WHERE id = %(id)s",
            parameters={"id": segment_id}
        )
        if existing.result_rows:
            updates = []
            params: dict[str, object] = {"id": segment_id}
            if image_b64:
                updates.append("image_data = %(image_data)s")
                updates.append("image_mime = %(image_mime)s")
                params["image_data"] = image_b64
                params["image_mime"] = image_mime
            if audio_b64:
                updates.append("audio_data = %(audio_data)s")
                updates.append("audio_mime = %(audio_mime)s")
                params["audio_data"] = audio_b64
                params["audio_mime"] = audio_mime
            if meta:
                updates.append("media_metadata = %(media_metadata)s")
                params["media_metadata"] = meta

            if updates:
                query = f"ALTER TABLE source_segment UPDATE {', '.join(updates)} WHERE id = %(id)s"
                ch_client.command(query, parameters=params)
            return True
        else:
            row = [
                segment_id,
                None,
                1,
                1,
                "",
                "",
                image_b64,
                image_mime,
                audio_b64,
                audio_mime,
                meta,
            ]
            columns = [
                "id", "graph_id", "chapter", "sequence", "original_text",
                "normalized_text", "image_data", "image_mime", "audio_data",
                "audio_mime", "media_metadata"
            ]
            ch_client.insert("source_segment", [row], column_names=columns)
            return True
    except Exception as e:
        logger.error("Failed to save segment media to ClickHouse", segment_id=segment_id, error=str(e))
        raise e


def get_segment_media(
    segment_id: str,
    media_type: str = "image",
    client: Client | None = None,
) -> tuple[bytes, str] | None:
    """
    Retrieves media bytes and MIME type for a specific source segment.
    media_type: 'image' or 'audio'
    """
    import base64
    ch_client = client if client is not None else get_clickhouse_client()

    col_data = "image_data" if media_type == "image" else "audio_data"
    col_mime = "image_mime" if media_type == "image" else "audio_mime"

    query = f"SELECT {col_data}, {col_mime} FROM source_segment WHERE id = %(id)s"
    res = ch_client.query(query, parameters={"id": segment_id})
    if not res.result_rows:
        return None

    raw_data, mime = res.result_rows[0]
    if not raw_data:
        return None

    if isinstance(raw_data, str):
        try:
            data_bytes = base64.b64decode(raw_data)
        except Exception:
            data_bytes = raw_data.encode("utf-8")
    elif isinstance(raw_data, bytes):
        data_bytes = raw_data
    else:
        return None

    return data_bytes, mime or ("image/png" if media_type == "image" else "audio/wav")


def get_segment_all_media(
    segment_id: str,
    client: Client | None = None,
) -> dict[str, object] | None:
    """
    Returns metadata and availability status of all media for a given source segment.
    """
    ch_client = client if client is not None else get_clickhouse_client()
    query = """
    SELECT id, graph_id, chapter, sequence, 
           length(image_data) > 0 as has_image, image_mime, length(image_data) as image_size,
           length(audio_data) > 0 as has_audio, audio_mime, length(audio_data) as audio_size,
           media_metadata
    FROM source_segment 
    WHERE id = %(id)s
    """
    res = ch_client.query(query, parameters={"id": segment_id})
    if not res.result_rows:
        return None

    row = res.result_rows[0]
    return {
        "segment_id": str(row[0]),
        "graph_id": str(row[1]) if row[1] else None,
        "chapter": row[2],
        "sequence": row[3],
        "has_image": bool(row[4]),
        "image_mime": row[5],
        "image_size_bytes": row[6],
        "has_audio": bool(row[7]),
        "audio_mime": row[8],
        "audio_size_bytes": row[9],
        "media_metadata": row[10] if len(row) > 10 else {},
    }
