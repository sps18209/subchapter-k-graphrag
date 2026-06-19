#!/usr/bin/env python3
"""
test_enrich.py — the gated-enrichment security property, offline and deterministic.

Proves: PROPOSE drafts a gloss but does NOT change the graph and is NOT citable;
only an attorney PROMOTE writes it; REJECT changes nothing. Uses the stub enricher,
so it runs with no key and no network.

    python test_enrich.py
"""
import graph
import retrieve
import enrich

passed = 0
def check(name, cond):
    global passed
    assert cond, "FAIL: " + name
    passed += 1
    print("  ok:", name)


def _status(con, nid):
    return con.execute("SELECT enrichment_status FROM node WHERE id=?", (nid,)).fetchone()[0]


def main():
    con = graph.build(":memory:")
    nid = "t_outside_basis"
    orig = graph.node(con, nid)["synthesis"]

    print("providers:")
    check("get_enricher default is off", enrich.get_enricher("none") is None)
    check("stub provider resolves", enrich.get_enricher("stub").name == "stub")
    try:
        enrich.OpenAIEnricher(api_key=None)
        check("openai requires a key", False)
    except RuntimeError:
        check("openai requires a key", True)

    print("propose is gated (no graph mutation, not citable):")
    prop = enrich.propose(con, nid, enrich.StubEnricher())
    check("draft is produced", prop["draft"].startswith(enrich.DRAFT_PREFIX))
    check("draft differs from the current note", prop["draft"] != orig)
    check("propose did NOT change the node", graph.node(con, nid)["synthesis"] == orig)
    check("node still marked structural", _status(con, nid) == "structural")
    r = retrieve.retrieve(con, "what feeds outside basis")
    surfaced = {n["citation"]: n["synthesis"] for n, _ in r["results"]}
    check("retrieval surfaces the ORIGINAL note, not the draft",
          surfaced.get("Outside basis") == orig)

    print("reject changes nothing:")
    enrich.reject(prop, "not accurate")
    check("graph unchanged after reject", graph.node(con, nid)["synthesis"] == orig)

    print("promote is the only writer, and it is attributed:")
    audit = enrich.promote(con, prop, attorney="J. Attorney")
    check("promote attributed to the attorney", audit["attorney"] == "J. Attorney")
    check("node synthesis now equals the approved draft", graph.node(con, nid)["synthesis"] == prop["draft"])
    check("node marked enriched", _status(con, nid) == "enriched")
    try:
        enrich.promote(con, prop, attorney="")
        check("promote refuses without an attorney", False)
    except ValueError:
        check("promote refuses without an attorney", True)

    print(f"\nALL {passed} ENRICHMENT CHECKS PASSED")


if __name__ == "__main__":
    main()
