"""
retrieve.py — Layer 3 GraphRAG retrieval.

Pipeline (matches the converged design and rag-architect's hybrid + rerank pattern):
  1. lexical SEED        — BM25 over node text (stdlib; a stand-in for embeddings)
  2. graph EXPANSION     — BFS 1-2 hops along typed edges; a computed-term hub pulls
                           its ENTIRE input DAG (the thing flat retrieval misses)
  3. authority RERANK    — sort by tier (statute > reg > ruling/case), relevance as tiebreak
  4. currency FILTER     — Layer 0 validity-interval gate, as-of a transaction date
  5. computation ROUTING — basis questions are handed to calculator.py, never reasoned out
  6. ASSEMBLE            — cited authority + relationships + a verify disclaimer

Pure stdlib. No network, no embedding download. Swap step 1 for embeddings in prod.
"""

from __future__ import annotations
import re
import math
import graph

_TOK = re.compile(r"[a-z0-9]+")
def _toks(s: str) -> list[str]:
    return _TOK.findall(s.lower())


class BM25:
    def __init__(self, docs: dict):
        self.ids = list(docs)
        self.tok = {i: _toks(docs[i]) for i in self.ids}
        self.dl = {i: len(self.tok[i]) for i in self.ids}
        self.avgdl = sum(self.dl.values()) / max(1, len(self.ids))
        self.df = {}
        for i in self.ids:
            for t in set(self.tok[i]):
                self.df[t] = self.df.get(t, 0) + 1
        self.N = len(self.ids)

    def _idf(self, t):
        n = self.df.get(t, 0)
        return math.log(1 + (self.N - n + 0.5) / (n + 0.5))

    def score(self, query, i, k1=1.5, b=0.75):
        tf = {}
        for t in self.tok[i]:
            tf[t] = tf.get(t, 0) + 1
        s = 0.0
        for t in _toks(query):
            if t in tf:
                s += self._idf(t) * (tf[t] * (k1 + 1)) / (tf[t] + k1 * (1 - b + b * self.dl[i] / self.avgdl))
        return s

    def topk(self, query, k=8):
        scored = [(self.score(query, i), i) for i in self.ids]
        scored = [x for x in scored if x[0] > 0]
        scored.sort(reverse=True)
        return scored[:k]


def _docs(con):
    out = {}
    for nid, cite, label, syn, tags in con.execute(
            "SELECT id,citation,label,synthesis,tags FROM node"):
        out[nid] = " ".join([cite, label, syn or "", (tags or "").replace("|", " "), nid.replace("_", " ")])
    return out


_COMPUTE = re.compile(r"\b(comput|calculat|figure|how much|what.+basis|ending basis|gain|suspend)", re.I)
def _is_computation(q: str) -> bool:
    return "basis" in q.lower() and bool(_COMPUTE.search(q))


def retrieve(con, question: str, as_of: str | None = None, seed_k: int = 8, top_n: int = 16) -> dict:
    bm = BM25(_docs(con))
    seeds = [i for _, i in bm.topk(question, seed_k)]

    # 2. expansion
    visited, frontier = set(seeds), list(seeds)
    for _ in range(2):
        nxt = []
        for nid in frontier:
            for e in graph.neighbors(con, nid):
                other = e["dst"] if e["src"] == nid else e["src"]
                if other not in visited:
                    visited.add(other)
                    nxt.append(other)
        frontier = nxt
    # computed-term hub: pull its whole DAG
    for nid in list(visited):
        n = graph.node(con, nid)
        if n and n["ntype"] == "term" and n["term_subtype"] == "computed":
            for e in graph.neighbors(con, nid):
                visited.add(e["dst"] if e["src"] == nid else e["src"])

    # protect the input DAG of any seed computed-hub so it survives truncation
    protected = set()
    for sid in seeds:
        sn = graph.node(con, sid)
        if sn and sn["ntype"] == "term" and sn["term_subtype"] == "computed":
            for e in graph.neighbors(con, sid):
                if e["dst"] == sid and e["etype"] in ("computes", "adjusts", "uses"):
                    protected.add(e["src"])
                if e["src"] == sid and e["etype"] == "overflow":
                    protected.add(e["dst"])

    def rel_of(nid):
        return bm.score(question, nid) + (5.0 if nid in protected else 0.0)

    # currency filter
    cand, excluded = [], []
    for nid in visited:
        if graph.applicable(con, nid, as_of):
            cand.append(nid)
        else:
            n = graph.node(con, nid)
            excluded.append((n["citation"], n["valid_from"], n["valid_to"]))

    # must-keep = applicable seeds + the full input DAG of any seed computed-hub
    cand_set = set(cand)
    must = [nid for nid in dict.fromkeys(list(seeds) + sorted(protected)) if nid in cand_set]
    # node id is the final tiebreak so truncation is deterministic (independent of set
    # iteration order / hash seed) and identical to the JS port — see web-src/parity_runner.js.
    others = sorted((c for c in cand if c not in set(must)),
                    key=lambda nid: (graph.node(con, nid)["tier"], -rel_of(nid), nid))
    keep = list(must)
    for nid in others:
        if len(keep) >= top_n:
            break
        keep.append(nid)

    # final display order: authority tier, then relevance, then id (deterministic tiebreak)
    results = sorted(((graph.node(con, nid), rel_of(nid)) for nid in keep),
                     key=lambda nr: (nr[0]["tier"], -nr[1], nr[0]["id"]))

    computed_hubs = [n for n, _ in results if n["ntype"] == "term" and n["term_subtype"] == "computed"]
    return {
        "question": question, "as_of": as_of,
        "results": results,
        "seeds": seeds, "excluded_by_currency": excluded,
        "computed_hubs": computed_hubs, "is_computation": _is_computation(question),
    }


def _dag(con, hub_id):
    """Ordered inbound computation edges for a computed-term hub, plus member ids."""
    rows, members = [], set()
    for e in graph.neighbors(con, hub_id):
        if e["dst"] == hub_id and e["etype"] in ("computes", "adjusts", "uses"):
            n = graph.node(con, e["src"])
            members.add(e["src"])
            rows.append((e["seq"] if e["seq"] is not None else 99, e["grp"] or "-",
                         e["direction"] or "-", n["citation"], e["mechanism"]))
        if e["src"] == hub_id and e["etype"] == "overflow":
            members.add(e["dst"])
    rows.sort()
    overflow = [graph.node(con, e["dst"])["citation"] + " (" + e["mechanism"] + ")"
                for e in graph.neighbors(con, hub_id) if e["src"] == hub_id and e["etype"] == "overflow"]
    return rows, overflow, members


def assemble(con, r: dict) -> str:
    L = [f"Q: {r['question']}"]
    if r["as_of"]:
        L.append(f"   (as of {r['as_of']})")
    L.append("")

    # build DAG blocks for any seed computed-hub; collect members to suppress from the flat list
    dag_blocks, suppressed = [], set()
    for hub in r["computed_hubs"]:
        if hub["id"] not in r["seeds"]:
            continue  # render the DAG only when the hub is actually the subject
        rows, overflow, members = _dag(con, hub["id"])
        if rows:
            suppressed |= members
            block = [f"COMPUTED TERM '{hub['label']}' — ordered input DAG:"]
            for seq, grp, direction, cite, mech in rows:
                tag = f"[{grp}/{direction}]"
                block.append(f"   {seq:>2}. {cite:<16} {tag:<24} {mech}")
            if overflow:
                block.append("   floor 0; overflow -> " + "; ".join(overflow))
            dag_blocks.append("\n".join(block))

    L.append("AUTHORITY NEIGHBORHOOD (by tier):")
    tier_name = {1: "statute", 3: "regulation", 4: "ruling/notice", 5: "form/program"}
    cur = None
    for n, rel in r["results"]:
        if n["id"] in suppressed:
            continue  # shown in the ordered DAG block instead
        if n["tier"] != cur:
            cur = n["tier"]
            L.append(f"  -- {tier_name.get(cur, 'tier ' + str(cur))} --")
        L.append(f"   {n['citation']:<26} {n['synthesis']}")

    for b in dag_blocks:
        L += ["", b]

    if r["is_computation"]:
        L += ["", "COMPUTATION DETECTED:",
              "   This needs a number. Route to the deterministic engine, not the model:",
              "   python query.py --compute --inputs '{\"beginning_basis\": ..., \"losses\": ...}'"]

    if r["excluded_by_currency"]:
        L += ["", "EXCLUDED (not in force / superseded as of date):"]
        for cite, vf, vt in r["excluded_by_currency"]:
            L.append(f"   {cite}  (window {vf or '-'} to {vt or '-'})")

    L += ["", "Assembled from graph seed (unverified). Cite only primary authority after attorney review."]
    return "\n".join(L)


if __name__ == "__main__":
    con = graph.build()
    for q in ["what feeds outside basis",
              "disguised sale of contributed property with a liability",
              "ordinary income when selling a partnership interest"]:
        print("=" * 78)
        print(assemble(con, retrieve(con, q)))
        print()
