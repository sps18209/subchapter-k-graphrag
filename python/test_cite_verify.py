#!/usr/bin/env python3
"""
test_cite_verify.py — the citation-verification gate, offline and deterministic.

Asserts: corpus citations verify as in_corpus; well-formed-but-absent cites are flagged
well_formed (not trusted); malformed cites are unrecognized; citations are classified by
type and extracted from prose; and a model draft referencing a fabricated cite is caught.

    python test_cite_verify.py
"""
import graph
import cite_verify as cv
import enrich

passed = 0
def check(name, cond):
    global passed
    assert cond, "FAIL: " + name
    passed += 1
    print("  ok:", name)


def main():
    con = graph.build(":memory:")
    corpus = cv.corpus_cites(con)

    print("classification:")
    check("IRC is a statute", cv.classify("IRC 704(d)") == "statute")
    check("Treas. Reg. is a regulation", cv.classify("Treas. Reg. 1.704-2") == "regulation")
    check("Rev. Rul. is a ruling", cv.classify("Rev. Rul. 2024-14") == "ruling")
    check("Notice is a ruling", cv.classify("Notice 2025-28") == "ruling")
    check("P.L. is a public law", cv.classify("P.L. 119-21") == "public_law")
    check("X v. Y is a case", cv.classify("Commissioner v. Culbertson") == "case")
    check("gibberish is unknown", cv.classify("see the thing") == "unknown")

    print("verification against the corpus:")
    check("a real corpus cite is in_corpus", cv.verify("IRC 704(d)", corpus)["status"] == "in_corpus")
    check("a well-formed absent cite is flagged, not trusted",
          cv.verify("IRC 9999(z)", corpus)["status"] == "well_formed")
    check("a malformed cite is unrecognized",
          cv.verify("totally made up", corpus)["status"] == "unrecognized")

    print("extraction from prose:")
    found = cv.extract_citations("Under IRC 752(a) and Rev. Rul. 2024-14, but cf. Notice 2025-28.")
    check("pulls statute / ruling / notice from text",
          {"IRC 752(a)", "Rev. Rul. 2024-14", "Notice 2025-28"} <= set(found))

    print("the enrichment gate catches a fabricated cite:")
    class BadEnricher:
        name = "bad"
        def propose_synthesis(self, node):
            return enrich.DRAFT_PREFIX + "This rests on IRC 9999(z), a section that does not exist."
    prop = enrich.propose(con, "t_outside_basis", BadEnricher())
    statuses = {c["citation"]: c["status"] for c in prop["cite_check"]}
    check("draft cite_check is attached", "cite_check" in prop)
    check("the fabricated cite is flagged well_formed/unrecognized (not in_corpus)",
          statuses.get("IRC 9999(z)") in ("well_formed", "unrecognized"))

    print(f"\nALL {passed} CITE-VERIFY CHECKS PASSED")


if __name__ == "__main__":
    main()
