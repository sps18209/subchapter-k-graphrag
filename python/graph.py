"""
graph.py — storage (SQLite stand-in for Postgres/Neo4j), the Layer 0 currency
verifier, and an integrity check. Pure stdlib.

The SQLite schema mirrors schema.sql (the production Postgres DDL). Building the
structural graph is deterministic and cheap; the LLM enrichment layer is a documented
hook (see enrich.py notes in README), not required to run anything here.
"""

from __future__ import annotations
import sqlite3
from datetime import date
import seed_subk
import seed_recent

DB = "subk.db"


def build(db_path: str = DB) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.executescript("""
        DROP TABLE IF EXISTS node; DROP TABLE IF EXISTS edge;
        CREATE TABLE node(
            id TEXT PRIMARY KEY, ntype TEXT, citation TEXT, label TEXT,
            tier INTEGER, term_subtype TEXT, synthesis TEXT, tags TEXT,
            valid_from TEXT, valid_to TEXT, enrichment_status TEXT DEFAULT 'structural');
        CREATE TABLE edge(
            src TEXT, dst TEXT, etype TEXT, direction TEXT, seq INTEGER,
            grp TEXT, mechanism TEXT, confidence REAL DEFAULT 1.0,
            created_by TEXT DEFAULT 'deterministic');
        CREATE INDEX i_edge_src ON edge(src);
        CREATE INDEX i_edge_dst ON edge(dst);
        CREATE INDEX i_node_tier ON node(tier);
    """)
    con.executemany(
        "INSERT INTO node(id,ntype,citation,label,tier,term_subtype,synthesis,tags,valid_from,valid_to)"
        " VALUES(?,?,?,?,?,?,?,?,?,?)",
        [(n[0], n[1], n[2], n[3], n[4], n[5], n[6], "|".join(n[7]), n[8], n[9])
         for n in (seed_subk.NODES + seed_recent.NODES)])
    con.executemany(
        "INSERT INTO edge(src,dst,etype,direction,seq,grp,mechanism) VALUES(?,?,?,?,?,?,?)",
        seed_subk.EDGES + seed_recent.EDGES)
    con.commit()
    return con


# --- Postgres read path (the production store) ---------------------------------
# The engine is written against the SQLite schema: tables `node`/`edge`, `?` params,
# tags as a "a|b|c" string, dates as ISO text. The production store (schema.sql, loaded
# by deploy/migrate_postgres.py) uses `tax_node`/`tax_edge`, `%s` params, a native
# TEXT[] tags column, and DATE columns. This thin wrapper makes a psycopg connection
# look EXACTLY like the SQLite one to the rest of the engine — it rewrites the SQL and
# normalizes the two divergent types — so node(), neighbors(), the currency gate, and
# retrieve.* run UNCHANGED against either store. Reads only.
import re as _re
from datetime import datetime as _datetime

_TABLE_RX = _re.compile(r"\b(node|edge)\b")


def _translate(sql: str) -> str:
    """SQLite-shaped query -> Postgres: node/edge -> tax_node/tax_edge, ? -> %s."""
    return _TABLE_RX.sub(lambda m: "tax_" + m.group(1), sql).replace("?", "%s")


def _norm_cell(v):
    if isinstance(v, list):                          # tags TEXT[] -> SQLite's "a|b|c"
        return "|".join(v)
    if isinstance(v, (date, _datetime)):             # DATE -> "YYYY-MM-DD"
        return v.isoformat()
    return v


class _Result:
    """Eager, type-normalized result set that quacks like a sqlite3 cursor."""
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


class _PgConnection:
    """Wraps a psycopg connection so the engine's SQLite-shaped queries just work."""
    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=()):
        with self._raw.cursor() as cur:
            cur.execute(_translate(sql), params)
            rows = [tuple(_norm_cell(v) for v in r) for r in cur.fetchall()] if cur.description else []
        return _Result(rows)

    def close(self):
        try:
            self._raw.close()
        except Exception:
            pass


def pg_connect(url: str) -> _PgConnection:
    """Open the production Postgres store and wrap it for the engine.
    psycopg is imported lazily so the SQLite path stays pure-stdlib."""
    try:
        import psycopg
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("psycopg not installed; run: pip install 'psycopg[binary]'") from e
    # client_encoding pinned to UTF-8: the corpus carries § and — regardless of the
    # server's locale, so never let the client fall back to an ASCII encoding.
    return _PgConnection(psycopg.connect(url, autocommit=True, client_encoding="UTF8"))


def integrity(con: sqlite3.Connection) -> list[str]:
    """Every edge endpoint must be a real node. Returns a list of problems."""
    ids = {r[0] for r in con.execute("SELECT id FROM node")}
    problems = []
    for src, dst, etype in con.execute("SELECT src,dst,etype FROM edge"):
        if src not in ids:
            problems.append(f"dangling src {src} ({etype})")
        if dst not in ids:
            problems.append(f"dangling dst {dst} ({etype})")
    return problems


def node(con, nid):
    r = con.execute("SELECT id,ntype,citation,label,tier,term_subtype,synthesis,tags,valid_from,valid_to"
                    " FROM node WHERE id=?", (nid,)).fetchone()
    if not r:
        return None
    keys = ["id", "ntype", "citation", "label", "tier", "term_subtype", "synthesis", "tags", "valid_from", "valid_to"]
    d = dict(zip(keys, r))
    d["tags"] = d["tags"].split("|") if d["tags"] else []
    return d


def neighbors(con, nid):
    """Edges touching nid, in both directions."""
    out = []
    for row in con.execute("SELECT src,dst,etype,direction,seq,grp,mechanism FROM edge WHERE src=? OR dst=?",
                           (nid, nid)):
        out.append(dict(zip(["src", "dst", "etype", "direction", "seq", "grp", "mechanism"], row)))
    return out


def superseded_by(con, nid):
    """If nid was revoked/removed/withdrawn, return (superseding_id, effective_date) else None."""
    row = con.execute(
        "SELECT e.src, n.valid_from FROM edge e JOIN node n ON n.id=e.src"
        " WHERE e.dst=? AND e.etype='supersedes' LIMIT 1", (nid,)).fetchone()
    return (row[0], row[1]) if row else None


def applicable(con, nid, as_of: str | None) -> bool:
    """Layer 0: is this node in force as of a date? (validity-interval + supersession gate)."""
    if as_of is None:
        return True
    n = node(con, nid)
    d = date.fromisoformat(as_of)
    if n["valid_from"] and d < date.fromisoformat(n["valid_from"]):
        return False
    if n["valid_to"] and d > date.fromisoformat(n["valid_to"]):
        return False
    sup = superseded_by(con, nid)
    if sup and sup[1] and d >= date.fromisoformat(sup[1]):
        return False
    return True


def currency_report(con, as_of: str) -> dict:
    """Flag every time-sensitive or superseded node as of a date."""
    d = date.fromisoformat(as_of)
    in_force, not_yet, expired, superseded = [], [], [], []
    seen = set()
    for nid, cite, vf, vt in con.execute(
            "SELECT id,citation,valid_from,valid_to FROM node WHERE valid_from IS NOT NULL OR valid_to IS NOT NULL"):
        seen.add(nid)
        sup = superseded_by(con, nid)
        if vf and d < date.fromisoformat(vf):
            not_yet.append((cite, f"effective {vf}"))
        elif vt and d > date.fromisoformat(vt):
            expired.append((cite, f"removed {vt}"))
        elif sup and sup[1] and d >= date.fromisoformat(sup[1]):
            superseded.append((cite, f"superseded by {node(con, sup[0])['citation']}"))
        else:
            in_force.append((cite, "in force"))
    # superseded nodes that have no interval of their own
    for nid, cite in con.execute("SELECT DISTINCT dst, '' FROM edge WHERE etype='supersedes'"):
        if nid in seen:
            continue
        sup = superseded_by(con, nid)
        c = node(con, nid)["citation"]
        if sup and sup[1] and d >= date.fromisoformat(sup[1]):
            superseded.append((c, f"superseded by {node(con, sup[0])['citation']}"))
        else:
            in_force.append((c, "in force"))
    return {"as_of": as_of, "in_force": in_force, "not_yet_effective": not_yet,
            "expired": expired, "superseded": superseded}


if __name__ == "__main__":
    con = build()
    probs = integrity(con)
    nn = con.execute("SELECT COUNT(*) FROM node").fetchone()[0]
    ne = con.execute("SELECT COUNT(*) FROM edge").fetchone()[0]
    print(f"built graph: {nn} nodes, {ne} edges; integrity problems: {len(probs)}")
    for p in probs:
        print("  !", p)
    print()
    for label, when in [("2016 (pre-TCJA)", "2016-06-01"), ("2020", "2020-06-01"),
                        ("2026 (post-OBBBA)", "2026-06-01"), ("2030", "2030-06-01")]:
        rep = currency_report(con, when)
        print(f"as of {label}:")
        for cite, why in rep["not_yet_effective"]:
            print(f"   NOT YET: {cite} ({why})")
        for cite, why in rep["expired"]:
            print(f"   REMOVED: {cite} ({why})")
        for cite, why in rep["superseded"]:
            print(f"   SUPERSEDED: {cite} ({why})")
