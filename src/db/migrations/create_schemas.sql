USE default;

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
    object_entity_id UUID
)
ENGINE = MergeTree()
ORDER BY (
    subject_entity_id,
    predicate,
    object_entity_id,
    id
);


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
    normalized_text String
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