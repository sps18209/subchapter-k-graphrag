-- schema.sql — the production Postgres DDL the SQLite runtime mirrors.
-- Definition-centric: TERM nodes are hubs; authority attaches by typed edges.

CREATE TABLE tax_node (
    id                TEXT PRIMARY KEY,
    ntype             TEXT NOT NULL CHECK (ntype IN ('term','provision','regulation','ruling','case')),
    citation          TEXT NOT NULL,
    label             TEXT NOT NULL,
    tier              INTEGER NOT NULL,        -- 1 statute, 3 regulation, 4 ruling/case, 5 form/program
    term_subtype      TEXT CHECK (term_subtype IN ('statutory','interpretive','computed')),
    synthesis         TEXT,                    -- original plain-law gloss; LLM-enrichable
    tags              TEXT[],
    valid_from        DATE,                    -- Layer 0 validity interval
    valid_to          DATE,
    enrichment_status TEXT NOT NULL DEFAULT 'structural'  -- structural | enriched
);

CREATE TABLE tax_edge (
    src         TEXT NOT NULL REFERENCES tax_node(id),
    dst         TEXT NOT NULL REFERENCES tax_node(id),
    etype       TEXT NOT NULL,   -- computes adjusts uses defines interprets informs implements
                                 -- cross_references overflow amends enacts supersedes
    direction   TEXT,            -- initialize | increase | decrease | constraint
    seq         INTEGER,         -- ordering within a computed-term DAG
    grp         TEXT,            -- increase | distribution | reduce | loss_limited
    mechanism   TEXT,
    confidence  REAL NOT NULL DEFAULT 1.0,
    created_by  TEXT NOT NULL DEFAULT 'deterministic'   -- deterministic | llm | attorney
);

CREATE INDEX i_edge_src   ON tax_edge(src);
CREATE INDEX i_edge_dst   ON tax_edge(dst);
CREATE INDEX i_edge_etype ON tax_edge(etype);
CREATE INDEX i_node_tier  ON tax_node(tier);

-- Production retrieval adds a vector column for Layer 3 dense seeding:
--   ALTER TABLE tax_node ADD COLUMN embedding vector(768);
--   CREATE INDEX ON tax_node USING hnsw (embedding vector_cosine_ops);
-- The SQLite runtime substitutes BM25 for this; everything else is identical.
