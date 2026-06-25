#!/usr/bin/env python3
"""
test_horizon.py — the proposed-legislation horizon scan, offline and deterministic.

Asserts the parsing/rendering that turns a govinfo BILLS hit into a labeled, linked entry,
and that the output is unmistakably marked NOT-authority. The live network search is not
exercised here (that needs the govinfo API); this covers everything deterministic.

    python test_horizon.py
"""
import horizon as h

passed = 0
def check(name, cond):
    global passed
    assert cond, "FAIL: " + name
    passed += 1
    print("  ok:", name)


def main():
    print("congress math (keeps the default from going stale):")
    check("2026 -> 119th Congress", h.current_congress(2026) == 119)
    check("2027 -> 120th Congress", h.current_congress(2027) == 120)

    print("package-id parsing:")
    check("senate bill", h._parse_package("BILLS-119s4330is") ==
          {"congress": "119", "type": "s", "number": "4330", "version": "is"})
    check("house bill w/ multi-letter type", h._parse_package("BILLS-119hr9172ih")["type"] == "hr")
    check("joint resolution type", h._parse_package("BILLS-118hjres1enr")["type"] == "hjres")
    check("garbage -> None", h._parse_package("not-a-package") is None)

    print("render a hit into a labeled, linked entry:")
    hit = h._render_hit({"packageId": "BILLS-119s4330is",
                         "title": "Ending the Carried Interest Loophole Act", "dateIssued": "2026-04-16"})
    check("bill label", hit["bill"] == "S. 4330")
    check("stage from version suffix", hit["stage"] == "introduced (Senate)")
    check("official congress.gov link", hit["url"] ==
          "https://www.congress.gov/bill/119th-congress/senate-bill/4330")
    check("enrolled suffix reads as passed-both-chambers",
          h._render_hit({"packageId": "BILLS-119hr1enr", "title": "x", "dateIssued": "2025-07-09"})["stage"]
          == "enrolled — passed both chambers")

    print("output is unmistakably marked NOT authority:")
    out = h.format_scan({"count": 30, "shown": 1, "congress": 119, "bills": [hit]})
    check("carries the NOT-law disclaimer", "NOT law" in out and "NOT authority" in out)
    check("shows the bill and its link", "S. 4330" in out and "congress.gov" in out)
    empty = h.format_scan({"count": 0, "shown": 0, "congress": 119, "bills": []})
    check("empty scan still warns + says none found", "NOT law" in empty and "no matching bills" in empty)

    print(f"\nALL {passed} HORIZON CHECKS PASSED")


if __name__ == "__main__":
    main()
