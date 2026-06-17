"""
test_subk.py — verifiable goals for the whole system. Run: python test_subk.py
Plain asserts, no third-party test runner.
"""
import graph
import retrieve
import calculator as calc

passed = 0
def check(name, cond):
    global passed
    assert cond, "FAIL: " + name
    passed += 1
    print("  ok:", name)


def test_calculator():
    print("calculator:")
    sally = calc.compute_outside_basis(calc.BasisInputs(beginning_basis=45000, losses=125000))
    check("Sally: loss allowed 45k", sally["sec704d_loss_allowed"] == 45000)
    check("Sally: loss suspended 80k", sally["sec704d_loss_suspended"] == 80000)
    joe = calc.compute_outside_basis(calc.BasisInputs(beginning_basis=245000, cash_distributed=465000))
    check("Joe: 731(a) gain 220k", joe["sec731a_gain"] == 220000)
    check("Joe: ending basis 0 (floor)", joe["ending_basis"] == 0)
    # ordering matters: a distribution strips basis that would have absorbed a loss
    ordered = calc.compute_outside_basis(calc.BasisInputs(beginning_basis=100, cash_distributed=100, losses=50))
    check("ordering: distribution first => loss fully suspended",
          ordered["sec704d_loss_suspended"] == 50 and ordered["ending_basis"] == 0)


def test_integrity(con):
    print("integrity:")
    check("no dangling edges", graph.integrity(con) == [])
    check("node count >= 70", con.execute("SELECT COUNT(*) FROM node").fetchone()[0] >= 70)


def test_retrieval(con):
    print("retrieval:")
    r = retrieve.retrieve(con, "what feeds outside basis")
    cites = {n["citation"] for n, _ in r["results"]}
    for needed in ["IRC 722", "IRC 733", "IRC 752(a)", "IRC 704(d)"]:
        check(f"basis query surfaces {needed}", needed in cites)
    check("basis query flags computation", r["is_computation"])

    r2 = retrieve.retrieve(con, "disguised sale of contributed property with a liability")
    cites2 = {n["citation"] for n, _ in r2["results"]}
    check("disguised-sale query surfaces IRC 707", "IRC 707" in cites2)

    r3 = retrieve.retrieve(con, "ordinary income selling a partnership interest hot assets")
    cites3 = {n["citation"] for n, _ in r3["results"]}
    check("hot-asset query surfaces IRC 751", "IRC 751" in cites3)


def test_currency(con):
    print("currency:")
    check("704(d)(3) not in force 2016", not graph.applicable(con, "s704d3", "2016-06-01"))
    check("704(d)(3) in force 2019", graph.applicable(con, "s704d3", "2019-06-01"))
    check("199A permanent: still in force 2030 (OBBBA)", graph.applicable(con, "s199A", "2030-06-01"))
    check("1062 not in force 2024", not graph.applicable(con, "s1062", "2024-06-01"))
    check("1062 in force 2026", graph.applicable(con, "s1062", "2026-06-01"))
    check("Rev Rul 2024-14 good law in 2024", graph.applicable(con, "rr2024_14", "2024-08-01"))
    check("Rev Rul 2024-14 superseded by 2026", not graph.applicable(con, "rr2024_14", "2026-01-01"))
    rep = graph.currency_report(con, "2026-06-01")
    supe = {c for c, _ in rep["superseded"]}
    check("2026 report flags Rev Rul 2024-14 superseded", "Rev. Rul. 2024-14" in supe)
    # §1.6011-18: Notice 2025-23 announced removal & waived penalties, but the section
    # remains codified in the eCFR (current through 6/12/2026) — still in force. (Corrected
    # June 2026 against the official eCFR; the prior seed wrongly recorded a 3/6/2026 removal.)
    check("1.6011-18 still in force 2026 (eCFR-confirmed)", graph.applicable(con, "reg6011_18", "2026-06-01"))
    exp = {c for c, _ in rep["expired"]}
    check("2026 report does NOT flag 1.6011-18 removed", "Treas. Reg. 1.6011-18" not in exp)


def test_recent(con):
    print("recent developments:")
    r = retrieve.retrieve(con, "CAMT corporate alternative minimum tax partnership AFSI")
    cites = {n["citation"] for n, _ in r["results"]}
    check("CAMT query surfaces Notice 2025-28", "Notice 2025-28" in cites)
    r2 = retrieve.retrieve(con, "qualified farmland installment election Form 1062")
    cites2 = {n["citation"] for n, _ in r2["results"]}
    check("farmland query surfaces IRC 1062", "IRC 1062" in cites2)
    r3 = retrieve.retrieve(con, "CAMT additional interim guidance partnership 56A AFSI")
    cites3 = {n["citation"] for n, _ in r3["results"]}
    check("CAMT query surfaces a post-2025-28 notice in the stack",
          any(c in cites3 for c in ["Notice 2025-46", "Notice 2025-49", "Notice 2026-7"]))


def test_densification(con):
    print("densification:")
    for nid in ["s751c", "s751d", "s736a", "s736b", "s732a2", "r1752_3_t2", "r1704_3d"]:
        check(f"leaf node {nid} present", graph.node(con, nid) is not None)
    # 2026 currency-maintenance additions (primary-source research)
    for nid in ["n2025_27", "n2025_46", "n2025_49", "n2026_07", "camt_propreg", "n2026_03"]:
        check(f"recent node {nid} present", graph.node(con, nid) is not None)


if __name__ == "__main__":
    con = graph.build()
    test_calculator()
    test_integrity(con)
    test_retrieval(con)
    test_currency(con)
    test_recent(con)
    test_densification(con)
    print(f"\nALL {passed} CHECKS PASSED")
