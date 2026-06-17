#!/usr/bin/env python3
"""
parity_test.py — prove the browser engine (web-src/engine.js) is a faithful port of
the authoritative Python engine (graph.py / retrieve.py / calculator.py).

The README claims the JS demo is "verified to parity with the Python." This makes that
claim reproducible: it runs a battery of retrieve / compute / currency / dag / applicable
cases through the Python engine, runs the SAME cases through engine.js via Node
(web-src/parity_runner.js), normalizes both identically, and asserts they match.

    cd python
    python parity_test.py            # requires `node` on PATH; exits non-zero on any mismatch

Why this matters: the demo embeds the engine and the corpus in a single HTML file. If the
JS port ever drifts from the Python system, the thing people actually open would quietly
disagree with the authoritative engine. This test is the guard against that drift.
"""
from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile

import graph
import retrieve
import calculator

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(ROOT, "web-src", "parity_runner.js")


def r6(x: float) -> float:
    return round(float(x) + 0.0, 6)


def _norm_row(row):
    return ["" if v is None else str(v) for v in row]


def _sorted_rows(rows):
    # element-wise sort of null-normalized rows; mirrors sortRows in parity_runner.js
    return sorted(_norm_row(r) for r in rows)


# ---- the case battery -------------------------------------------------------

def build_cases(con) -> list[dict]:
    cases: list[dict] = []

    queries = [
        ("what feeds a partner's outside basis", None),
        ("what feeds outside basis", "2026-06-01"),
        ("disguised sale of contributed property with a liability", "2016-06-01"),
        ("disguised sale of contributed property with a liability", None),
        ("hot assets ordinary income selling a partnership interest", None),
        ("CAMT corporate alternative minimum tax adjustments", "2026-06-01"),
        ("farmland qualified family farm gain", "2026-06-01"),
        ("guaranteed payment for services", None),
        ("section 704(d) loss limitation suspended", "2016-06-01"),
        ("how much is the ending basis and the gain", None),
        ("liquidating distribution of property to a partner", "2020-06-01"),
        ("section 199A qualified business income deduction", "2030-06-01"),
    ]
    for q, as_of in queries:
        cases.append({"type": "retrieve", "question": q, "as_of": as_of})

    computes = [
        {"beginning_basis": 245000, "cash_distributed": 465000},                       # Joe (LB&I)
        {"beginning_basis": 45000, "losses": 125000},                                  # Sally (LB&I)
        {"beginning_basis": 100000, "cash_contributed": 20000, "liability_increase": 30000,
         "income_taxable": 15000, "income_tax_exempt": 5000, "cash_distributed": 40000,
         "nondeductible": 3000, "losses": 90000},                                       # full waterfall
        {"beginning_basis": 0, "property_contributed_basis": 50000, "liability_decrease": 80000},  # floor + §731(a)
        {"beginning_basis": 10000},                                                     # no activity
    ]
    for inp in computes:
        cases.append({"type": "compute", "inputs": inp})

    for as_of in ["2016-06-01", "2020-06-01", "2024-06-01", "2026-06-01", "2030-06-01"]:
        cases.append({"type": "currency", "as_of": as_of})

    # a dag case for every computed-term hub in the graph
    hubs = [r[0] for r in con.execute(
        "SELECT id FROM node WHERE ntype='term' AND term_subtype='computed' ORDER BY id")]
    for hub in hubs:
        cases.append({"type": "dag", "hub": hub})

    # applicable() over every node across the full date span — the currency-gate core
    node_ids = [r[0] for r in con.execute("SELECT id FROM node ORDER BY id")]
    for nid in node_ids:
        for as_of in [None, "2016-06-01", "2024-06-01", "2026-06-01", "2030-06-01"]:
            cases.append({"type": "applicable", "id": nid, "as_of": as_of})

    return cases


# ---- the Python side, normalized to match parity_runner.js ------------------

def run_python(con, c: dict) -> dict:
    t = c["type"]
    if t == "retrieve":
        out = retrieve.retrieve(con, c["question"], c["as_of"])
        return {
            "type": "retrieve", "question": c["question"], "as_of": c["as_of"],
            "results": [[n["citation"], n["tier"], r6(rel)] for n, rel in out["results"]],
            "seeds": list(out["seeds"]),
            "excluded": _sorted_rows([[e[0], e[1], e[2]] for e in out["excluded_by_currency"]]),
            "computed_hubs": [n["citation"] for n in out["computed_hubs"]],
            "is_computation": out["is_computation"],
        }
    if t == "compute":
        out = calculator.compute_outside_basis(calculator.BasisInputs(**c["inputs"]))
        return {
            "type": "compute", "inputs": c["inputs"],
            "ending": r6(out["ending_basis"]), "gain": r6(out["sec731a_gain"]),
            "loss_allowed": r6(out["sec704d_loss_allowed"]),
            "loss_suspended": r6(out["sec704d_loss_suspended"]),
        }
    if t == "currency":
        out = graph.currency_report(con, c["as_of"])
        return {
            "type": "currency", "as_of": c["as_of"],
            "in_force": _sorted_rows(out["in_force"]), "not_yet": _sorted_rows(out["not_yet_effective"]),
            "expired": _sorted_rows(out["expired"]), "superseded": _sorted_rows(out["superseded"]),
        }
    if t == "dag":
        rows, overflow, _ = retrieve._dag(con, c["hub"])
        return {
            "type": "dag", "hub": c["hub"],
            "rows": [[seq, grp, direction, cite, mech] for seq, grp, direction, cite, mech in rows],
            "overflow": list(overflow),
        }
    if t == "applicable":
        return {"type": "applicable", "id": c["id"], "as_of": c["as_of"],
                "value": graph.applicable(con, c["id"], c["as_of"])}
    raise ValueError(f"unknown case type {t}")


# ---- driver -----------------------------------------------------------------

def main() -> int:
    con = graph.build(":memory:")
    cases = build_cases(con)

    py = [run_python(con, c) for c in cases]

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(cases, f)
        cases_path = f.name
    try:
        proc = subprocess.run(["node", RUNNER, cases_path],
                              capture_output=True, text=True)
    except FileNotFoundError:
        print("ERROR: `node` not found on PATH. Install Node.js to run the parity test.",
              file=sys.stderr)
        return 2
    finally:
        os.unlink(cases_path)

    if proc.returncode != 0:
        print("ERROR: parity_runner.js failed:\n" + proc.stderr, file=sys.stderr)
        return 2
    js = json.loads(proc.stdout)

    # round-trip Python through JSON so dict/list/number types compare identically
    py = json.loads(json.dumps(py))

    label = {"retrieve": lambda c: f"retrieve {c['question']!r} as_of={c['as_of']}",
             "compute": lambda c: f"compute {c['inputs']}",
             "currency": lambda c: f"currency as_of={c['as_of']}",
             "dag": lambda c: f"dag {c['hub']}",
             "applicable": lambda c: f"applicable {c['id']} as_of={c['as_of']}"}

    failures = 0
    by_type: dict[str, int] = {}
    for c, p, j in zip(cases, py, js):
        by_type[c["type"]] = by_type.get(c["type"], 0) + 1
        if p == j:
            continue
        failures += 1
        print(f"\nMISMATCH — {label[c['type']](c)}")
        for k in p:
            if p[k] != j.get(k):
                print(f"   field {k!r}")
                print(f"     python: {json.dumps(p[k])}")
                print(f"     js    : {json.dumps(j.get(k))}")

    total = len(cases)
    print(f"\nparity cases by type: " +
          ", ".join(f"{k}={v}" for k, v in sorted(by_type.items())))
    if failures:
        print(f"\nPARITY FAILED — {failures}/{total} cases differ between engine.js and Python.")
        return 1
    print(f"\nPARITY OK — all {total} cases agree between engine.js and the Python engine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
