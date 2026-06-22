#!/usr/bin/env python3
"""
test_assistant.py — the natural-language front door, offline (rules router).

Checks that plain-English messages route to the right deterministic tool and that the
engine — not the router — produces the answer. No model, no network.

    python test_assistant.py
"""
import graph
import assistant as a

passed = 0
def check(name, cond):
    global passed
    assert cond, "FAIL: " + name
    passed += 1
    print("  ok:", name)


def main():
    con = graph.build(":memory:")

    print("intent parsing:")
    check("valid JSON parses", a.parse_intent('{"tool":"verify","args":{"as_of":"2026-06-01"}}')["tool"] == "verify")
    check("garbage returns None", a.parse_intent("not json") is None)

    print("rules routing:")
    check("a question -> ask", a._rules_route("what feeds outside basis")["tool"] == "ask")
    r = a._rules_route("is the QBI deduction still in force as of 2030-06-01")
    check("currency phrasing + date -> verify", r["tool"] == "verify" and r["args"]["as_of"] == "2030-06-01")
    check("'list the terms' -> hubs", a._rules_route("list the terms")["tool"] == "hubs")
    check("compute phrasing + numbers -> compute",
          a._rules_route("compute the ending basis, losses were 125000")["tool"] == "compute")
    check("date inside a question is carried as as_of",
          a._rules_route("what changed by 2026-06-01")["args"]["as_of"] == "2026-06-01")
    sr = a._rules_route("what does Treas. Reg. 1.704-2 say")
    check("'what does X say' -> source with the full citation",
          sr["tool"] == "source" and sr["args"]["citation"] == "Treas. Reg. 1.704-2")

    print("the engine produces the answer (router only routes):")
    ask_out = a.run(con, {"tool": "ask", "args": {"question": "what feeds outside basis"}}, interactive=False)
    check("ask returns the authority neighborhood", "AUTHORITY NEIGHBORHOOD" in ask_out)
    ver_out = a.run(con, {"tool": "verify", "args": {"as_of": "2026-06-01"}}, interactive=False)
    check("verify reports in-force authority", "IN FORCE" in ver_out and "2026-06-01" in ver_out)
    comp = a.run(con, {"tool": "compute", "args": {"beginning_basis": 245000, "cash_distributed": 465000}}, interactive=False)
    check("compute returns the deterministic figure (220,000 gain)", "220,000" in comp)
    cite_out = a.run(con, {"tool": "cite", "args": {"citation": "IRC 704(d)"}}, interactive=False)
    check("cite verifies a real corpus citation", "in_corpus" in cite_out)
    check("bad date is handled gracefully",
          "need a date" in a.run(con, {"tool": "verify", "args": {"as_of": "nope"}}, interactive=False))

    print("a simulated model intent routes + executes end to end:")
    intent = a.parse_intent('{"tool":"compute","args":{"beginning_basis":45000,"losses":125000}}')
    out = a.run(con, intent, interactive=False)
    check("model JSON -> §704(d) suspended 80,000", "80,000" in out)

    print(f"\nALL {passed} ASSISTANT CHECKS PASSED")


if __name__ == "__main__":
    main()
