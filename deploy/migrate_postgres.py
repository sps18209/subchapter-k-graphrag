"""
migrate_postgres.py — provision the production store.

Loads schema.sql (the production Postgres DDL: tax_node / tax_edge) into the database
named by DATABASE_URL, then inserts the same seed corpus the SQLite runtime builds.
This is the concrete SQLite -> Postgres swap: schema.sql is already the prod DDL, so
the data does not change shape; only the engine.

After running this you have a populated Postgres. Reading from it is already wired: start
the API with the same DATABASE_URL set and engine_adapter._connect returns
graph.pg_connect(url) — a wrapper that rewrites the SQLite-shaped queries (`?`->`%s`,
node/edge->tax_node/tax_edge) and normalizes DATE/TEXT[] columns, so the endpoints,
serialization, retrieval logic, and currency gate do not move. test_postgres_parity.py
proves the two stores return identical results. The dense-retrieval upgrade (BM25 ->
embeddings) is the vector column noted at the bottom of schema.sql.

Run:  DATABASE_URL=postgresql://user:pass@host:5432/db python migrate_postgres.py
Deps: pip install -r requirements-migrate.txt
"""

from __future__ import annotations

import os
import sys


def _engine_dir() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    for c in (os.environ.get("SUBK_ENGINE_DIR"),
              os.path.join(here, "..", "python"),
              os.path.join(here, ".."),
              os.path.join(here, "python")):
        if c and os.path.exists(os.path.join(c, "graph.py")):
            return os.path.abspath(c)
    sys.exit("Could not locate the engine directory (no graph.py found).")


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Set DATABASE_URL, e.g. postgresql://user:pass@host:5432/db")

    try:
        import psycopg  # lazy: the API does not need this
    except ImportError:
        sys.exit("psycopg not installed. Run: pip install -r requirements-migrate.txt")

    engine_dir = _engine_dir()
    sys.path.insert(0, engine_dir)
    import seed_subk
    import seed_recent
    import retrieve
    import embeddings

    with open(os.path.join(engine_dir, "schema.sql"), "r") as f:
        ddl = f.read()

    nodes = seed_subk.NODES + seed_recent.NODES
    edges = seed_subk.EDGES + seed_recent.EDGES

    # Optional dense layer (swap #2): when SUBK_EMBED_PROVIDER is set, persist a pgvector
    # column + HNSW index. Uses the SAME doc text as BM25 and the in-memory dense index.
    embedder = embeddings.get_embedder()

    # client_encoding pinned to UTF-8 — the seed text carries § and — characters.
    with psycopg.connect(url, client_encoding="UTF8") as con:
        with con.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS tax_edge CASCADE; DROP TABLE IF EXISTS tax_node CASCADE;")
            cur.execute(ddl)
            cur.executemany(
                "INSERT INTO tax_node"
                "(id,ntype,citation,label,tier,term_subtype,synthesis,tags,valid_from,valid_to)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [(n[0], n[1], n[2], n[3], n[4], n[5], n[6], list(n[7]), n[8], n[9]) for n in nodes],
            )
            cur.executemany(
                "INSERT INTO tax_edge(src,dst,etype,direction,seq,grp,mechanism)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s)",
                edges,
            )
            if embedder is not None:
                texts = [retrieve.doc_text(n[2], n[3], n[6], "|".join(n[7]), n[0]) for n in nodes]
                vecs = embedder.embed_many(texts)
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute(f"ALTER TABLE tax_node ADD COLUMN IF NOT EXISTS embedding vector({embedder.dim})")
                cur.executemany(
                    "UPDATE tax_node SET embedding = %s::vector WHERE id = %s",
                    [("[" + ",".join(f"{x:.7f}" for x in v) + "]", n[0]) for v, n in zip(vecs, nodes)],
                )
                cur.execute("CREATE INDEX IF NOT EXISTS i_node_embedding ON tax_node "
                            "USING hnsw (embedding vector_cosine_ops)")
        con.commit()
        with con.cursor() as cur:
            nn = cur.execute("SELECT COUNT(*) FROM tax_node").fetchone()[0]
            ne = cur.execute("SELECT COUNT(*) FROM tax_edge").fetchone()[0]
            dangling = cur.execute(
                "SELECT COUNT(*) FROM tax_edge e WHERE NOT EXISTS"
                " (SELECT 1 FROM tax_node n WHERE n.id=e.src)"
                " OR NOT EXISTS (SELECT 1 FROM tax_node n WHERE n.id=e.dst)"
            ).fetchone()[0]

    emb_note = f", embeddings stored ({embedder.name}, dim {embedder.dim}, pgvector + HNSW)" \
        if embedder is not None else ""
    print(f"migrated to Postgres: {nn} nodes, {ne} edges, dangling edges {dangling}{emb_note}")
    print("Done. Start the API with this same DATABASE_URL set and it reads from Postgres "
          "(graph.pg_connect); leave DATABASE_URL unset to serve from SQLite.")


if __name__ == "__main__":
    main()
