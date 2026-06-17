"""
migrate_postgres.py — provision the production store.

Loads schema.sql (the production Postgres DDL: tax_node / tax_edge) into the database
named by DATABASE_URL, then inserts the same seed corpus the SQLite runtime builds.
This is the concrete SQLite -> Postgres swap: schema.sql is already the prod DDL, so
the data does not change shape; only the engine.

After running this you have a populated Postgres. The remaining wire is to point
engine_adapter._connect at this database (return a psycopg connection) and switch the
handful of `?` placeholders in graph.py / retrieve.py to `%s`, and table names node/edge
to tax_node/tax_edge. The endpoints, serialization, retrieval logic, and currency gate
do not move. The dense-retrieval upgrade (BM25 -> embeddings) is the vector column noted
at the bottom of schema.sql.

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

    with open(os.path.join(engine_dir, "schema.sql"), "r") as f:
        ddl = f.read()

    nodes = seed_subk.NODES + seed_recent.NODES
    edges = seed_subk.EDGES + seed_recent.EDGES

    with psycopg.connect(url) as con:
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
        con.commit()
        with con.cursor() as cur:
            nn = cur.execute("SELECT COUNT(*) FROM tax_node").fetchone()[0]
            ne = cur.execute("SELECT COUNT(*) FROM tax_edge").fetchone()[0]
            dangling = cur.execute(
                "SELECT COUNT(*) FROM tax_edge e WHERE NOT EXISTS"
                " (SELECT 1 FROM tax_node n WHERE n.id=e.src)"
                " OR NOT EXISTS (SELECT 1 FROM tax_node n WHERE n.id=e.dst)"
            ).fetchone()[0]

    print(f"migrated to Postgres: {nn} nodes, {ne} edges, dangling edges {dangling}")
    print("NOTE: the API still reads via the SQLite adapter until engine_adapter._connect "
          "is pointed at this database (see this file's docstring).")


if __name__ == "__main__":
    main()
