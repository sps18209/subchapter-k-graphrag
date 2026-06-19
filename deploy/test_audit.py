#!/usr/bin/env python3
"""
test_audit.py — the hash-chained audit trail is tamper-evident.

Asserts: a sequence of logged records forms an intact chain; altering a field, changing a
principal, reordering, or dropping a record all break verification. Pure stdlib.

    python test_audit.py
"""
import copy

import audit

passed = 0
def check(name, cond):
    global passed
    assert cond, "FAIL: " + name
    passed += 1
    print("  ok:", name)


def main():
    # reset the module chain state for a clean run
    audit._state = {"seq": 0, "prev": audit.GENESIS}
    recs = []
    for i in range(5):
        recs.append(audit.audit_log(request_id=f"r{i}", principal="firm",
                                    action="POST /ask", status=200, duration_ms=1.0 + i,
                                    detail={"question": f"q{i}"}))

    print("a clean chain verifies:")
    ok, msg = audit.verify_chain(recs)
    check("intact chain verifies", ok)
    check("links are sequential", [r["seq"] for r in recs] == [0, 1, 2, 3, 4])
    check("each record chains to the prior hash", all(recs[i]["prev"] == recs[i - 1]["hash"] for i in range(1, 5)))

    print("tampering is detected:")
    altered = copy.deepcopy(recs)
    altered[2]["principal"] = "attacker"            # change who did it
    ok, msg = audit.verify_chain(altered)
    check("altered field breaks the chain", not ok and "seq 2" in msg)

    altered = copy.deepcopy(recs)
    altered[3]["detail"]["question"] = "redacted"   # change what was asked
    ok, _ = audit.verify_chain(altered)
    check("altered detail breaks the chain", not ok)

    dropped = [r for r in recs if r["seq"] != 2]    # excise a record
    ok, _ = audit.verify_chain(dropped)
    check("a dropped record breaks the chain", not ok)

    reordered = [recs[0], recs[2], recs[1], recs[3], recs[4]]
    ok, _ = audit.verify_chain(reordered)
    check("reordering breaks the chain", not ok)

    print(f"\nALL {passed} AUDIT CHECKS PASSED")


if __name__ == "__main__":
    main()
