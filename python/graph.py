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
