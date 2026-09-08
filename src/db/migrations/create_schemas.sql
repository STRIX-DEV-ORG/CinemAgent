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
    description String DEFAULT '',

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

    description String DEFAULT '',

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
ALTER TABLE knowledge_element ADD COLUMN IF NOT EXISTS description String DEFAULT '';
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
