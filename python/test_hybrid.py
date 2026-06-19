#!/usr/bin/env python3
"""
test_hybrid.py — hybrid (dense + lexical) retrieval, offline and deterministic.

Uses the pure-stdlib HashingEmbedder so it runs everywhere with no network or install.
Asserts: the dense channel is deterministic; fusing it with BM25 (Reciprocal Rank Fusion)
recovers a node that pure BM25 misses; and the default (dense=None) path is unchanged.

    python test_hybrid.py
"""
import graph
import retrieve
import embeddings as emb

passed = 0
def check(name, cond):
    global passed
    assert cond, "FAIL: " + name
    passed += 1
    print("  ok:", name)


def main():
    con = graph.build(":memory:")
    docs = retrieve._docs(con)
    embedder = emb.HashingEmbedder()
    idx = emb.DenseIndex.from_docs(embedder, docs)

    print("embedder:")
    v = embedder.embed("outside basis")
    check("vectors are L2-normalized", abs(sum(x * x for x in v) - 1.0) < 1e-9)
    check("embedder is deterministic", embedder.embed("hot assets") == embedder.embed("hot assets"))
    idx2 = emb.DenseIndex.from_docs(embedder, docs)
    check("dense index is deterministic", idx.vectors == idx2.vectors)
    check("get_embedder default is off (BM25-only)", emb.get_embedder(None) is None or emb.get_embedder("none") is None)

    print("dense recovers a node BM25 misses:")
    bm = retrieve.BM25(docs)
    # "capitalaccount" has no whitespace, so it is one BM25 token that matches nothing...
    check("BM25 finds nothing for 'capitalaccount'", bm.topk("capitalaccount", 8) == [])
    r0 = retrieve.retrieve(con, "capitalaccount")                 # BM25-only
    check("BM25-only retrieval returns nothing", len(r0["results"]) == 0)
    # ...but the hashing embedder's character n-grams overlap "capital account".
    r1 = retrieve.retrieve(con, "capitalaccount", dense=idx)      # hybrid
    cites = {n["citation"] for n, _ in r1["results"]}
    check("hybrid surfaces the capital-account hub", "704(b) book capital account" in cites)
    check("hybrid retrieval is non-empty", len(r1["results"]) > 0)

    print("hybrid keeps lexical results and is deterministic:")
    h = retrieve.retrieve(con, "what feeds outside basis", dense=idx)
    hcites = {n["citation"] for n, _ in h["results"]}
    for needed in ["IRC 722", "IRC 733", "IRC 704(d)"]:
        check(f"hybrid still surfaces {needed}", needed in hcites)
    order1 = [n["citation"] for n, _ in retrieve.retrieve(con, "disguised sale liability", dense=idx)["results"]]
    order2 = [n["citation"] for n, _ in retrieve.retrieve(con, "disguised sale liability", dense=idx)["results"]]
    check("hybrid retrieval is deterministic", order1 == order2)

    print("default path is unchanged:")
    a = [n["citation"] for n, _ in retrieve.retrieve(con, "hot assets ordinary income")["results"]]
    b = [n["citation"] for n, _ in retrieve.retrieve(con, "hot assets ordinary income", dense=None)["results"]]
    check("dense=None == omitting dense", a == b)

    print(f"\nALL {passed} HYBRID CHECKS PASSED")


if __name__ == "__main__":
    main()
