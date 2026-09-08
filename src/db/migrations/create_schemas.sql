-- =========================================================
-- NARRATIVE GRAPH
-- =========================================================

CREATE TABLE IF NOT EXISTS narrative_graph
(
    id UUID DEFAULT generateUUIDv4(),

    name String,
    version UInt32 DEFAULT 1,

    created_at DateTime64(3) DEFAULT now64(3),
    updated_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree()
ORDER BY id;


-- =========================================================
-- ENTITY
-- =========================================================

CREATE TABLE IF NOT EXISTS entity
(
    id UUID DEFAULT generateUUIDv4(),

    graph_id UUID,

    name String,
    type LowCardinality(String),
    status LowCardinality(String),
    description String DEFAULT '',
    content String DEFAULT '',

    confidence Float32 DEFAULT 1.0,

    aliases Array(String) DEFAULT [],
    metadata JSON
)
ENGINE = MergeTree()
ORDER BY (graph_id, type, id);


-- =========================================================
-- TIME
-- =========================================================

CREATE TABLE IF NOT EXISTS time
(
    id UUID DEFAULT generateUUIDv4(),

    graph_id UUID,

    type LowCardinality(String),
    value String,
    precision LowCardinality(String),

    metadata JSON
)
ENGINE = MergeTree()
ORDER BY (graph_id, type, id);


-- =========================================================
-- CONTEXT
-- =========================================================

CREATE TABLE IF NOT EXISTS context
(
    id UUID DEFAULT generateUUIDv4(),

    graph_id UUID,

    type LowCardinality(String),
    name String DEFAULT '',
    description String DEFAULT '',
    content String DEFAULT '',

    holder_entity_id Nullable(UUID),

    confidence Float32 DEFAULT 1.0,

    metadata JSON
)
ENGINE = MergeTree()
ORDER BY (graph_id, type, id);


-- =========================================================
-- EVENT
-- =========================================================

CREATE TABLE IF NOT EXISTS event
(
    id UUID DEFAULT generateUUIDv4(),

    graph_id UUID,
    time_id Nullable(UUID),

    name String,
    type LowCardinality(String),
    status LowCardinality(String),

    description String,
    content String DEFAULT '',

    confidence Float32 DEFAULT 1.0,

    metadata JSON
)
ENGINE = MergeTree()
ORDER BY (graph_id, type, id);


-- =========================================================
-- EVENT PARTICIPANT
-- =========================================================

CREATE TABLE IF NOT EXISTS event_participant
(
    id UUID DEFAULT generateUUIDv4(),

    event_id UUID,
    entity_id UUID,

    role LowCardinality(String)
)
ENGINE = MergeTree()
ORDER BY (event_id, role, entity_id);


-- =========================================================
-- KNOWLEDGE ELEMENT
-- =========================================================

CREATE TABLE IF NOT EXISTS knowledge_element
(
    id UUID DEFAULT generateUUIDv4(),

    graph_id UUID,

    time_id Nullable(UUID),
    context_id Nullable(UUID),

    element_type LowCardinality(String),
    name String DEFAULT '',

    description String DEFAULT '',
    content String DEFAULT '',

    origin LowCardinality(String),
    status LowCardinality(String),

    confidence Float32 DEFAULT 1.0,

    metadata JSON
)
ENGINE = MergeTree()
ORDER BY (graph_id, element_type, id);


-- =========================================================
-- ATTRIBUTE
--
-- IMPORTANT:
-- id is the SAME id as knowledge_element.id.
-- Do not generate a second UUID here.
-- =========================================================

CREATE TABLE IF NOT EXISTS attribute
(
    id UUID,

    owner_entity_id UUID,

    name LowCardinality(String),
    value JSON
)
ENGINE = MergeTree()
ORDER BY (owner_entity_id, name, id);


-- =========================================================
-- STATEMENT
--
-- IMPORTANT:
-- id is the SAME id as knowledge_element.id.
-- =========================================================

CREATE TABLE IF NOT EXISTS statement
(
    id UUID,

    subject_entity_id UUID,
    predicate LowCardinality(String),
    object_entity_id UUID,
    description String DEFAULT '',
    status LowCardinality(String) DEFAULT 'active',
    confidence Float32 DEFAULT 1.0,
    metadata JSON DEFAULT '{}'
)
ENGINE = MergeTree()
ORDER BY (
    subject_entity_id,
    predicate,
    object_entity_id,
    id
);

-- Add richer narrative fields for databases created before these columns existed.
ALTER TABLE entity ADD COLUMN IF NOT EXISTS description String DEFAULT '';
ALTER TABLE context ADD COLUMN IF NOT EXISTS description String DEFAULT '';
ALTER TABLE context ADD COLUMN IF NOT EXISTS name String DEFAULT '';
ALTER TABLE context ADD COLUMN IF NOT EXISTS content String DEFAULT '';
ALTER TABLE knowledge_element ADD COLUMN IF NOT EXISTS description String DEFAULT '';
ALTER TABLE knowledge_element ADD COLUMN IF NOT EXISTS name String DEFAULT '';
ALTER TABLE knowledge_element ADD COLUMN IF NOT EXISTS content String DEFAULT '';
ALTER TABLE entity ADD COLUMN IF NOT EXISTS content String DEFAULT '';
ALTER TABLE event ADD COLUMN IF NOT EXISTS content String DEFAULT '';
ALTER TABLE statement ADD COLUMN IF NOT EXISTS description String DEFAULT '';
ALTER TABLE statement ADD COLUMN IF NOT EXISTS status LowCardinality(String) DEFAULT 'active';
ALTER TABLE statement ADD COLUMN IF NOT EXISTS confidence Float32 DEFAULT 1.0;
ALTER TABLE statement ADD COLUMN IF NOT EXISTS metadata JSON DEFAULT '{}';


-- =========================================================
-- GRAPH RELATION
--
-- A relation is a first-class edge between any two narrative nodes. A
-- statement relation also has matching knowledge_element and statement rows;
-- contextual relations remain independent edges.
-- =========================================================

CREATE TABLE IF NOT EXISTS graph_relation
(
    id UUID,
    graph_id UUID,
    source_node_id UUID,
    target_node_id UUID,
    relation_type LowCardinality(String),
    label String,
    description String DEFAULT '',
    status LowCardinality(String) DEFAULT 'active',
    confidence Float32 DEFAULT 1.0,
    metadata JSON DEFAULT '{}'
)
ENGINE = MergeTree()
ORDER BY (graph_id, relation_type, source_node_id, target_node_id, id);


-- =========================================================
-- EVENT EFFECT
-- =========================================================

CREATE TABLE IF NOT EXISTS event_effect
(
    id UUID DEFAULT generateUUIDv4(),

    event_id UUID,
    knowledge_element_id UUID,

    operation LowCardinality(String)
)
ENGINE = MergeTree()
ORDER BY (
    event_id,
    operation,
    knowledge_element_id
);


-- =========================================================
-- EVENT RELATION
-- =========================================================

CREATE TABLE IF NOT EXISTS event_relation
(
    id UUID DEFAULT generateUUIDv4(),

    source_event_id UUID,
    target_event_id UUID,

    type LowCardinality(String),

    confidence Float32 DEFAULT 1.0
)
ENGINE = MergeTree()
ORDER BY (
    source_event_id,
    type,
    target_event_id
);


-- =========================================================
-- SOURCE SEGMENT
-- =========================================================

CREATE TABLE IF NOT EXISTS source_segment
(
    id UUID DEFAULT generateUUIDv4(),

    graph_id UUID,

    chapter UInt32,
    sequence UInt32,

    original_text String,
    normalized_text String,

    image_data String DEFAULT '',
    image_mime String DEFAULT 'image/png',
    audio_data String DEFAULT '',
    audio_mime String DEFAULT 'audio/wav',
    media_metadata Map(String, String) DEFAULT map()
)
ENGINE = MergeTree()
ORDER BY (
    graph_id,
    chapter,
    sequence,
    id
);


-- =========================================================
-- EVIDENCE
-- =========================================================

CREATE TABLE IF NOT EXISTS evidence
(
    id UUID DEFAULT generateUUIDv4(),

    source_segment_id UUID,

    excerpt String,

    confidence Float32 DEFAULT 1.0,

    start_offset UInt32,
    end_offset UInt32
)
ENGINE = MergeTree()
ORDER BY (
    source_segment_id,
    start_offset,
    id
);


-- =========================================================
-- ELEMENT EVIDENCE
--
-- Polymorphic relation:
--
-- target_type:
--   ENTITY
--   EVENT
--   KNOWLEDGE
--
-- target_id contains the UUID of the corresponding object.
-- =========================================================

CREATE TABLE IF NOT EXISTS element_evidence
(
    id UUID DEFAULT generateUUIDv4(),

    evidence_id UUID,

    target_type LowCardinality(String),
    target_id UUID
)
ENGINE = MergeTree()
ORDER BY (
    target_type,
    target_id,
    evidence_id
);


-- Accepted agent/UI write batches. Individual operations are immutable;
-- status fields are updated by the materializer as ClickHouse mutations.
CREATE TABLE IF NOT EXISTS operation_batch
(
    id UUID,
    graph_id UUID,
    idempotency_key String,
    status LowCardinality(String),
    operation_count UInt32,
    error Nullable(String),
    created_at DateTime64(3) DEFAULT now64(3),
    updated_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree()
ORDER BY (graph_id, id);


CREATE TABLE IF NOT EXISTS graph_operation
(
    id UUID,
    batch_id UUID,
    graph_id UUID,
    sequence UInt32,
    operation_type LowCardinality(String),
    payload JSON,
    provenance JSON,
    origin LowCardinality(String),
    status LowCardinality(String),
    error Nullable(String),
    created_at DateTime64(3) DEFAULT now64(3),
    applied_at Nullable(DateTime64(3))
)
ENGINE = MergeTree()
ORDER BY (batch_id, sequence, id);


-- Writer workspace documents. Revisions are append-only; reads use FINAL.
CREATE TABLE IF NOT EXISTS story_chapter
(
    id UUID,
    graph_id UUID,
    title String,
    sequence UInt32,
    document_json String,
    plain_text String,
    revision UInt32,
    created_at DateTime64(3) DEFAULT now64(3),
    updated_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(revision)
ORDER BY (graph_id, id);


-- Global graph nodes can be associated with many chapter workspaces.
CREATE TABLE IF NOT EXISTS chapter_node
(
    graph_id UUID,
    chapter_id UUID,
    node_id UUID,
    node_type LowCardinality(String),
    created_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree()
ORDER BY (graph_id, chapter_id, node_type, node_id);


CREATE TABLE IF NOT EXISTS chapter_analysis_run
(
    id UUID,
    graph_id UUID,
    chapter_id UUID,
    chapter_revision UInt32,
    status LowCardinality(String),
    error Nullable(String),
    created_at DateTime64(3) DEFAULT now64(3),
    updated_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (graph_id, chapter_id, id);


CREATE TABLE IF NOT EXISTS chapter_analysis_proposal
(
    id UUID,
    run_id UUID,
    graph_id UUID,
    chapter_id UUID,
    operation_type LowCardinality(String),
    payload JSON,
    provenance JSON,
    status LowCardinality(String) DEFAULT 'proposed',
    created_at DateTime64(3) DEFAULT now64(3),
    updated_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (run_id, id);


-- Durable writer-facing AI work.  Results are JSON so every source agent can
-- expose its own structured output without a schema migration per model.
CREATE TABLE IF NOT EXISTS agent_run
(
    id UUID,
    graph_id UUID,
    chapter_id Nullable(UUID),
    agent_group LowCardinality(String),
    scope LowCardinality(String),
    input JSON,
    status LowCardinality(String),
    progress UInt8,
    message String,
    error Nullable(String),
    result JSON,
    created_at DateTime64(3) DEFAULT now64(3),
    updated_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (graph_id, id);


CREATE TABLE IF NOT EXISTS agent_artifact
(
    id UUID,
    run_id UUID,
    graph_id UUID,
    chapter_id Nullable(UUID),
    kind LowCardinality(String),
    title String,
    storage_url String,
    mime_type String,
    metadata JSON,
    created_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree()
ORDER BY (graph_id, run_id, id);


-- Immutable source of truth for writer, agent, and system activity. Event IDs
-- are sortable ULIDs generated by the API so replay can use a stable cursor.
CREATE TABLE IF NOT EXISTS narrative_event
(
    event_id String,
    graph_id UUID,
    chapter_id Nullable(UUID),
    batch_id Nullable(UUID),
    operation_id Nullable(UUID),
    event_type LowCardinality(String),
    actor_type LowCardinality(String),
    version UInt64,
    payload JSON,
    provenance JSON,
    occurred_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (graph_id, occurred_at, event_id);


-- Canonical chunks for story-scoped semantic retrieval. The application uses a
-- fixed 768-dimension embedder today; a model change creates a new model name
-- and reindexes rather than mixing dimensions in this index.
CREATE TABLE IF NOT EXISTS narrative_embedding
(
    id UUID,
    graph_id UUID,
    chapter_id Nullable(UUID),
    source_type LowCardinality(String),
    source_id String,
    source_version UInt64 DEFAULT 1,
    content_hash FixedString(64),
    content String,
    model LowCardinality(String),
    embedding Array(Float32),
    metadata JSON,
    created_at DateTime64(3) DEFAULT now64(3),
    INDEX embedding_hnsw embedding TYPE vector_similarity('hnsw', 'cosineDistance', 768)
)
ENGINE = MergeTree()
ORDER BY (graph_id, source_type, source_id, source_version, id);


-- Incremental activity aggregate used by the developer ClickHouse view.
CREATE TABLE IF NOT EXISTS story_activity_daily
(
    graph_id UUID,
    day Date,
    event_type LowCardinality(String),
    event_count UInt64
)
ENGINE = SummingMergeTree()
ORDER BY (graph_id, day, event_type);

CREATE MATERIALIZED VIEW IF NOT EXISTS story_activity_daily_mv
TO story_activity_daily AS
SELECT graph_id, toDate(occurred_at) AS day, event_type, count() AS event_count
FROM narrative_event
GROUP BY graph_id, day, event_type;


-- Event-derived read models.  These are intentionally parallel to the
-- pre-existing graph tables while stories are migrated and parity-checked.
CREATE TABLE IF NOT EXISTS narrative_projection_checkpoint
(
    projector LowCardinality(String),
    graph_id UUID,
    cursor_at DateTime64(3),
    cursor_event_id String,
    status LowCardinality(String),
    error Nullable(String),
    updated_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (projector, graph_id);

CREATE TABLE IF NOT EXISTS narrative_chapter_current
(
    graph_id UUID,
    id UUID,
    title String,
    sequence UInt32,
    document_json String,
    plain_text String,
    revision UInt64,
    is_deleted UInt8 DEFAULT 0,
    event_id String,
    updated_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(revision)
ORDER BY (graph_id, id);

CREATE TABLE IF NOT EXISTS narrative_node_current
(
    graph_id UUID,
    id UUID,
    node_type LowCardinality(String),
    name String,
    status LowCardinality(String),
    payload JSON,
    version UInt64,
    is_deleted UInt8 DEFAULT 0,
    event_id String,
    updated_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(version)
ORDER BY (graph_id, id);

CREATE TABLE IF NOT EXISTS narrative_relation_current
(
    graph_id UUID,
    id UUID,
    source_node_id UUID,
    target_node_id UUID,
    relation_type LowCardinality(String),
    label String,
    status LowCardinality(String),
    payload JSON,
    version UInt64,
    is_deleted UInt8 DEFAULT 0,
    event_id String,
    updated_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(version)
ORDER BY (graph_id, id);

CREATE TABLE IF NOT EXISTS narrative_membership_current
(
    graph_id UUID,
    chapter_id UUID,
    node_id UUID,
    node_type LowCardinality(String),
    version UInt64,
    is_deleted UInt8 DEFAULT 0,
    event_id String,
    updated_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(version)
ORDER BY (graph_id, chapter_id, node_id, node_type);

CREATE TABLE IF NOT EXISTS narrative_query_telemetry
(
    id UUID DEFAULT generateUUIDv4(),
    operation LowCardinality(String),
    graph_id UUID DEFAULT toUUID('00000000-0000-0000-0000-000000000000'),
    duration_ms UInt32,
    success UInt8,
    error String DEFAULT '',
    rows_returned UInt32 DEFAULT 0,
    occurred_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(occurred_at)
ORDER BY (operation, occurred_at, graph_id)
TTL occurred_at + INTERVAL 30 DAY;

CREATE TABLE IF NOT EXISTS agent_run_daily
(
    graph_id UUID,
    day Date,
    agent_group LowCardinality(String),
    status LowCardinality(String),
    run_count UInt64
)
ENGINE = SummingMergeTree()
ORDER BY (graph_id, day, agent_group, status);

CREATE MATERIALIZED VIEW IF NOT EXISTS agent_run_daily_mv
TO agent_run_daily AS
SELECT graph_id, toDate(occurred_at) AS day,
       JSONExtractString(payload, 'agent_group') AS agent_group,
       JSONExtractString(payload, 'status') AS status,
       count() AS run_count
FROM narrative_event
WHERE event_type = 'agent_run_updated'
GROUP BY graph_id, day, agent_group, status;

CREATE TABLE IF NOT EXISTS relation_activity_daily
(
    graph_id UUID,
    day Date,
    chapter_id UUID DEFAULT toUUID('00000000-0000-0000-0000-000000000000'),
    relation_type LowCardinality(String),
    event_count UInt64
)
ENGINE = SummingMergeTree()
ORDER BY (graph_id, day, chapter_id, relation_type);

CREATE MATERIALIZED VIEW IF NOT EXISTS relation_activity_daily_mv
TO relation_activity_daily AS
SELECT graph_id, toDate(occurred_at) AS day, ifNull(chapter_id, toUUID('00000000-0000-0000-0000-000000000000')) AS chapter_id,
       JSONExtractString(payload, 'relation_type') AS relation_type,
       count() AS event_count
FROM narrative_event
WHERE event_type IN ('create_relation', 'update_relation', 'delete_relation')
GROUP BY graph_id, day, chapter_id, relation_type;

CREATE TABLE IF NOT EXISTS story_health_snapshot
(
    graph_id UUID,
    chapters UInt32,
    nodes UInt32,
    relations UInt32,
    isolated_nodes_estimate UInt32,
    unresolved_assumptions UInt32,
    evidence_count UInt32,
    evidence_coverage Float32,
    projection_event_id String,
    calculated_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(calculated_at)
ORDER BY graph_id;

ALTER TABLE story_health_snapshot ADD COLUMN IF NOT EXISTS evidence_count UInt32 DEFAULT 0;

-- Per-story rollout and recoverable deletion state.  Keeping these separate
-- from canonical payloads makes cutover and purge administration explicit.
CREATE TABLE IF NOT EXISTS narrative_projection_rollout
(
    graph_id UUID,
    projected_reads_enabled UInt8 DEFAULT 0,
    parity_status LowCardinality(String) DEFAULT 'pending',
    parity_details JSON DEFAULT '{}',
    updated_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY graph_id;

CREATE TABLE IF NOT EXISTS narrative_story_deletion
(
    graph_id UUID,
    deleted_at Nullable(DateTime64(3)),
    purge_after Nullable(DateTime64(3)),
    restored_at Nullable(DateTime64(3)),
    purged_at Nullable(DateTime64(3)),
    event_id String,
    updated_at DateTime64(3) DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY graph_id;

ALTER TABLE narrative_embedding ADD COLUMN IF NOT EXISTS is_active UInt8 DEFAULT 1;
