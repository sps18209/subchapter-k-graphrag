#!/usr/bin/env python3
"""
test_postgres_parity.py — prove the Postgres production store returns results
IDENTICAL to the SQLite engine, so the SQLite -> Postgres swap changes nothing a
caller can observe.

It (1) builds the SQLite graph in memory, (2) loads schema.sql + the SAME seed into
the Postgres named by DATABASE_URL, then (3) runs node / neighbors / applicable /
currency_report / retrieve through the real graph.py + retrieve.py against BOTH
connections and asserts equality. No store-specific logic is duplicated — both runs go
through graph.pg_connect's wrapper vs. a plain sqlite3 connection.

    DATABASE_URL=postgresql://user:pass@host:5432/db python test_postgres_parity.py

SKIPS (exit 0) when DATABASE_URL is unset or psycopg is missing, so it is safe in a
suite that does not always have a database. Needs psycopg (pip install 'psycopg[binary]').
"""
from __future__ import annotations
import os
import sys

import graph
import retrieve


def _skip(msg: str):
    print("SKIP:", msg)
    sys.exit(0)


def _key(t):
    # order-independent, None-safe sort key for rows of mixed str/None/int
    return tuple("" if x is None else str(x) for x in t)


def _migrate_pg(url: str):
    """Load schema.sql + the seed corpus into Postgres (same shape as migrate_postgres.py)."""
    import psycopg
    import seed_subk
    import seed_recent
    here = os.path.dirname(os.path.abspath(__file__))
    ddl = open(os.path.join(here, "schema.sql")).read()
    nodes = seed_subk.NODES + seed_recent.NODES
    edges = seed_subk.EDGES + seed_recent.EDGES
    with psycopg.connect(url, autocommit=True) as con:
        with con.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS tax_edge CASCADE; DROP TABLE IF EXISTS tax_node CASCADE;")
            cur.execute(ddl)
            cur.executemany(
                "INSERT INTO tax_node(id,ntype,citation,label,tier,term_subtype,synthesis,tags,valid_from,valid_to)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [(n[0], n[1], n[2], n[3], n[4], n[5], n[6], list(n[7]), n[8], n[9]) for n in nodes],
            )
            cur.executemany(
                "INSERT INTO tax_edge(src,dst,etype,direction,seq,grp,mechanism) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                edges,
            )


def _sorted_neighbors(ns):
    return sorted(ns, key=lambda e: (e["src"], e["dst"], e["etype"]))


def _retr(con, q, as_of=None):
    r = retrieve.retrieve(con, q, as_of=as_of)
    return {
        "results": [(n["citation"], n["tier"], round(rel, 6)) for n, rel in r["results"]],
        "seeds": list(r["seeds"]),
        "computed_hubs": [h["citation"] for h in r["computed_hubs"]],
        "is_computation": r["is_computation"],
        "excluded": sorted((tuple(x) for x in r["excluded_by_currency"]), key=_key),
    }


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        _skip("set DATABASE_URL to run (e.g. postgresql://user:pass@host:5432/db)")
    try:
        import psycopg  # noqa: F401
    except ImportError:
        _skip("psycopg not installed (pip install 'psycopg[binary]')")

    lite = graph.build(":memory:")
    _migrate_pg(url)
    pg = graph.pg_connect(url)

    fails = 0
    def eq(name, a, b):
        nonlocal fails
        if a != b:
            fails += 1
            print(f"  MISMATCH {name}:\n    sqlite: {a}\n    pg    : {b}")

    eq("integrity", graph.integrity(lite), graph.integrity(pg))

    ids = [r[0] for r in lite.execute("SELECT id FROM node ORDER BY id")]
    dates = [None, "2016-06-01", "2024-06-01", "2026-06-01", "2030-06-01"]

    for nid in ids:
        eq(f"node {nid}", graph.node(lite, nid), graph.node(pg, nid))
        eq(f"neighbors {nid}", _sorted_neighbors(graph.neighbors(lite, nid)),
           _sorted_neighbors(graph.neighbors(pg, nid)))
        for d in dates:
            eq(f"applicable {nid} {d}", graph.applicable(lite, nid, d), graph.applicable(pg, nid, d))

    def cr(con, d):
        rep = graph.currency_report(con, d)
        return {k: sorted((tuple(x) for x in v), key=_key) for k, v in rep.items() if k != "as_of"}
    for d in dates[1:]:
        eq(f"currency {d}", cr(lite, d), cr(pg, d))

    queries = ["what feeds outside basis", "disguised sale of contributed property with a liability",
               "hot assets ordinary income selling a partnership interest", "CAMT partnership AFSI 56A",
               "section 704(d) loss limitation suspended", "qualified farmland installment 1062"]
    for q in queries:
        for d in [None, "2016-06-01", "2026-06-01"]:
            eq(f"retrieve {q!r} {d}", _retr(lite, q, d), _retr(pg, q, d))

    pg.close()
    print(f"\ncompared {len(ids)} nodes x {len(dates)} dates + currency + "
          f"{len(queries)} queries across both stores")
    if fails:
        print(f"STORE PARITY FAILED — {fails} mismatches between SQLite and Postgres")
        return 1
    print("STORE PARITY OK — SQLite and Postgres return identical results")
    return 0


if __name__ == "__main__":
    sys.exit(main())
