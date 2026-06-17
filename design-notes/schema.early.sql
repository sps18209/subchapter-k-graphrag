-- schema.sql — Tax Authority GraphRAG storage layer
-- Mirrors legal-ai-shared-infra conventions: Postgres is source of truth, audit
-- columns everywhere, validity intervals for temporal reasoning, authority tier as
-- a first-class property, assumption registry + audit log reused, hard-gate views.
-- Neo4j (optional) is a read replica for deep traversal; never the source of truth.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;        -- pgvector, semantic layer only

-- Authority tier: lower = stronger. 1 statute, 2 legislative reg, 3 interpretive reg,
-- 4 rev rul / rev proc / precedential case, 5 sub-reg guidance (notice/announcement),
-- 6 PLR / TAM (NON-precedential, IRC 6110(k)(3) -- never retrieved as authority).
CREATE TABLE tax_node (
    id                TEXT PRIMARY KEY,                 -- citation slug, stable
    node_type         TEXT NOT NULL CHECK (node_type IN
                        ('provision','regulation','ruling','case','defined_term')),
    citation          TEXT NOT NULL,
    label             TEXT,
    body              TEXT,
    authority_tier    SMALLINT NOT NULL,
    jurisdiction      TEXT NOT NULL DEFAULT 'US',
    -- temporal validity. valid_to IS NULL  ==  currently in force.
    valid_from        DATE,
    valid_to          DATE,
    enrichment_status TEXT NOT NULL DEFAULT 'structural'
                        CHECK (enrichment_status IN ('structural','enriched')),
    embedding         vector(1024),                     -- NULL until Layer 2 enriches
    source_uri        TEXT,
    created_by        TEXT NOT NULL DEFAULT 'deterministic'
                        CHECK (created_by IN ('deterministic','llm','attorney')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at        TIMESTAMPTZ,
    version           INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE tax_edge (
    id          TEXT PRIMARY KEY,                       -- src--type--dst, stable
    src_id      TEXT NOT NULL REFERENCES tax_node(id),
    dst_id      TEXT NOT NULL REFERENCES tax_node(id),
    edge_type   TEXT NOT NULL CHECK (edge_type IN (
                  'cross_references','cites','defines','defined_in',
                  'implements','applies','interprets',
                  'amended_by','supersedes','modifies','obsoletes','clarifies')),
    valid_from  DATE,
    valid_to    DATE,
    confidence  REAL NOT NULL DEFAULT 1.0,              -- 1.0 deterministic; <1 = llm
    created_by  TEXT NOT NULL DEFAULT 'deterministic'
                  CHECK (created_by IN ('deterministic','llm','attorney')),
    source_uri  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at  TIMESTAMPTZ
);

-- Reused from legal-ai-shared-infra (scoped to a research question, not a matter).
CREATE TABLE tax_assumption (
    id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    question_id  TEXT NOT NULL,
    text         TEXT NOT NULL,         -- e.g. "transaction closed before 2018-01-01"
    status       TEXT NOT NULL DEFAULT 'open'
                   CHECK (status IN ('open','verified','rejected')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE tax_audit_log (
    id          BIGSERIAL PRIMARY KEY,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    target_id   TEXT,
    before      JSONB,
    after       JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes (FKs, currency filter, vector search, tier ranking).
CREATE INDEX idx_node_type        ON tax_node(node_type)        WHERE deleted_at IS NULL;
CREATE INDEX idx_node_current     ON tax_node(authority_tier)   WHERE valid_to IS NULL AND deleted_at IS NULL;
CREATE INDEX idx_node_embedding   ON tax_node USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_edge_src         ON tax_edge(src_id)           WHERE deleted_at IS NULL;
CREATE INDEX idx_edge_dst         ON tax_edge(dst_id)           WHERE deleted_at IS NULL;
CREATE INDEX idx_edge_supersede   ON tax_edge(dst_id)
    WHERE edge_type IN ('supersedes','modifies','obsoletes') AND deleted_at IS NULL;

-- Layer 0 hard gate: any node that has been superseded/obsoleted and whose validity
-- has lapsed. A citation hitting this view is a HARD BLOCK, same posture as the
-- citation-verifier gate in the litigation suite.
CREATE VIEW v_stale_authority AS
SELECT n.id, n.citation, n.valid_to, e.edge_type AS killed_by, e.src_id AS killed_by_node
FROM tax_node n
JOIN tax_edge e ON e.dst_id = n.id
WHERE e.edge_type IN ('supersedes','modifies','obsoletes')
  AND e.deleted_at IS NULL
  AND (n.valid_to IS NOT NULL AND n.valid_to < CURRENT_DATE);

-- Current authority as of an arbitrary date is parameterized in the query layer:
--   WHERE valid_from <= :as_of AND (valid_to IS NULL OR valid_to >= :as_of)
CREATE VIEW v_current_authority AS
SELECT * FROM tax_node
WHERE valid_to IS NULL AND deleted_at IS NULL;

CREATE VIEW v_open_assumptions AS
SELECT * FROM tax_assumption WHERE status = 'open';
