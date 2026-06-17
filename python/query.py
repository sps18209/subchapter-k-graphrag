#!/usr/bin/env python3
"""
query.py — the Subchapter K GraphRAG CLI.

  python query.py "what feeds outside basis"
  python query.py "is the QBI deduction available" --asof 2030-01-01
  python query.py --compute --inputs '{"beginning_basis":245000,"cash_distributed":465000}'
  python query.py --verify 2016-06-01
  python query.py --build           # (re)build the graph from seed

The graph knows the law and points to the calculator; the calculator does the math.
"""

from __future__ import annotations
import argparse
import json
import os
import graph
import retrieve
import calculator as calc

DB = "subk.db"


def _con(rebuild=False):
    if rebuild or not os.path.exists(DB):
        return graph.build(DB)
    import sqlite3
    return sqlite3.connect(DB)


def main():
    ap = argparse.ArgumentParser(description="Subchapter K GraphRAG")
    ap.add_argument("question", nargs="?", help="natural-language question")
    ap.add_argument("--asof", help="transaction date YYYY-MM-DD (currency gate)")
    ap.add_argument("--compute", action="store_true", help="run the deterministic basis engine")
    ap.add_argument("--inputs", help="JSON of BasisInputs fields for --compute")
    ap.add_argument("--verify", metavar="DATE", help="currency report as of DATE")
    ap.add_argument("--build", action="store_true", help="rebuild the graph from seed")
    args = ap.parse_args()

    con = _con(rebuild=args.build)

    if args.build and not (args.question or args.compute or args.verify):
        nn = con.execute("SELECT COUNT(*) FROM node").fetchone()[0]
        ne = con.execute("SELECT COUNT(*) FROM edge").fetchone()[0]
        print(f"built: {nn} nodes, {ne} edges, integrity problems {len(graph.integrity(con))}")
        return

    if args.compute:
        fields = json.loads(args.inputs) if args.inputs else {}
        result = calc.compute_outside_basis(calc.BasisInputs(**fields))
        print(calc.format_result(result))
        return

    if args.verify:
        rep = graph.currency_report(con, args.verify)
        print(f"Currency report as of {rep['as_of']}:")
        for label, key in [("IN FORCE", "in_force"), ("NOT YET EFFECTIVE", "not_yet_effective"),
                           ("REMOVED/EXPIRED", "expired"), ("SUPERSEDED/REVOKED", "superseded")]:
            if rep[key]:
                print(f"  {label}:")
                for cite, why in rep[key]:
                    print(f"    {cite:<22} {why}")
        return

    if not args.question:
        ap.print_help()
        return

    print(retrieve.assemble(con, retrieve.retrieve(con, args.question, as_of=args.asof)))


if __name__ == "__main__":
    main()
