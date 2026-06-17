#!/usr/bin/env python3
"""
tui.py — interactive terminal UI for the Subchapter K GraphRAG engine.

A pure-stdlib REPL over the same engine the CLI and web demo use. Ask authority
questions, explore term hubs and their computation DAGs, run the deterministic
basis calculator, and move the "as of" date to watch the currency gate turn
authority on and off — all without leaving the terminal.

    cd python
    python tui.py            # then type `help`, or just type a question

No install, no network. Reuses graph.py / retrieve.py / calculator.py, so it can
never disagree with the CLI or the web demo. Colors auto-disable when the output
is not a TTY or when NO_COLOR is set.
"""
from __future__ import annotations
import cmd
import dataclasses
import json
import os
import sys
from datetime import date

import graph
import retrieve
import calculator as calc

# ---- tiny ANSI helper (no dependency; off for pipes / NO_COLOR) -------------
_USE_COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ
def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _USE_COLOR else s
def BOLD(s): return _c("1", s)
def DIM(s):  return _c("2", s)
def CY(s):   return _c("36", s)
def GR(s):   return _c("32", s)
def YE(s):   return _c("33", s)
def RE(s):   return _c("31", s)

TIER = {1: "statute", 3: "regulation", 4: "ruling/notice", 5: "form/program"}


class SubKShell(cmd.Cmd):
    intro = "\n".join([
        BOLD("Subchapter K · GraphRAG — interactive terminal UI"),
        DIM("Pure stdlib over the same engine as the CLI and web demo."),
        "Commands: " + CY("ask asof verify compute hubs hub node help quit"),
        DIM("Tip: just type a question (no `ask` needed). Set a date with `asof 2026-06-01`."),
        YE("Everything here is UNVERIFIED SEED for attorney review — not legal or tax advice."),
        "",
    ])

    def __init__(self):
        super().__init__()
        self.con = graph.build(":memory:")
        self.as_of: str | None = None
        nn = self.con.execute("SELECT COUNT(*) FROM node").fetchone()[0]
        ne = self.con.execute("SELECT COUNT(*) FROM edge").fetchone()[0]
        self.intro += DIM(f"graph: {nn} nodes, {ne} edges\n")
        self._set_prompt()

    def _set_prompt(self):
        self.prompt = CY(f"subk[{self.as_of or 'no date'}]> ")

    # ---- commands -----------------------------------------------------------
    def do_ask(self, arg):
        "ask <question> — authority neighborhood by tier (uses the current as-of date)"
        q = arg.strip() or input("question: ").strip()
        if not q:
            return
        print(retrieve.assemble(self.con, retrieve.retrieve(self.con, q, as_of=self.as_of)))

    def do_asof(self, arg):
        "asof [YYYY-MM-DD|clear] — show or set the transaction date for the currency gate"
        a = arg.strip()
        if not a:
            print(f"as-of date: {self.as_of or '(none — all authority shown)'}")
            return
        if a == "clear":
            self.as_of = None
            self._set_prompt()
            print("as-of cleared")
            return
        try:
            date.fromisoformat(a)
        except ValueError:
            print(RE("  bad date — use YYYY-MM-DD"))
            return
        self.as_of = a
        self._set_prompt()
        print(f"as-of set to {a}")

    def do_verify(self, arg):
        "verify [YYYY-MM-DD] — currency report as of a date (defaults to the as-of date)"
        a = arg.strip() or self.as_of
        if not a:
            print(RE("  give a date: verify 2026-06-01   (or set one with `asof`)"))
            return
        try:
            date.fromisoformat(a)
        except ValueError:
            print(RE("  bad date — use YYYY-MM-DD"))
            return
        rep = graph.currency_report(self.con, a)
        print(BOLD(f"Currency report as of {a}:"))
        for label, key, color in [("IN FORCE", "in_force", GR), ("NOT YET EFFECTIVE", "not_yet_effective", YE),
                                   ("REMOVED/EXPIRED", "expired", RE), ("SUPERSEDED/REVOKED", "superseded", RE)]:
            rows = rep[key]
            if rows:
                print("  " + color(label + ":"))
                for cite, why in rows:
                    print(f"    {cite:<26} " + DIM(why))

    def do_compute(self, arg):
        "compute [json] — deterministic outside-basis engine; no arg = interactive prompts"
        fields = {}
        arg = arg.strip()
        if arg:
            try:
                fields = json.loads(arg)
            except json.JSONDecodeError as e:
                print(RE(f"  bad JSON: {e}"))
                return
        else:
            print(DIM("  enter dollar amounts; blank = 0; Ctrl-C to cancel"))
            try:
                for f in dataclasses.fields(calc.BasisInputs):
                    raw = input(f"  {f.name} [0]: ").strip().replace(",", "").replace("$", "")
                    if raw:
                        fields[f.name] = float(raw)
            except (KeyboardInterrupt, EOFError):
                print("\n  cancelled")
                return
            except ValueError:
                print(RE("  not a number — cancelled"))
                return
        try:
            r = calc.compute_outside_basis(calc.BasisInputs(**fields))
        except TypeError as e:
            print(RE(f"  unknown input field: {e}"))
            return
        print(calc.format_result(r))

    def do_hubs(self, arg):
        "hubs — list term hubs (computed terms, which carry an input DAG, marked with *)"
        rows = self.con.execute(
            "SELECT id,citation,label,term_subtype FROM node WHERE ntype='term' "
            "ORDER BY (term_subtype='computed') DESC, id").fetchall()
        for nid, cite, label, sub in rows:
            mark = GR("*") if sub == "computed" else " "
            print(f" {mark} {CY(f'{nid:<22}')} {cite}  " + DIM("— " + label))
        print(DIM(f"  {len(rows)} hubs; * = computed term. Try: hub t_outside_basis"))

    def do_hub(self, arg):
        "hub <id> — a term hub: its computation DAG (if computed) + connected authority"
        nid = arg.strip()
        if not nid:
            print(RE("  usage: hub <id>   (see `hubs`)"))
            return
        n = graph.node(self.con, nid)
        if not n:
            print(RE(f"  no node '{nid}'   (see `hubs`)"))
            return
        print(BOLD(f"{n['citation']} — {n['label']}  ({nid})"))
        if n["synthesis"]:
            print(f"  {n['synthesis']}")
        rows, overflow, members = retrieve._dag(self.con, nid)
        if rows:
            print(BOLD("\n  ordered input DAG:"))
            for seq, grp, direction, cite, mech in rows:
                tag = f"[{grp}/{direction}]"
                print(f"    {seq:>2}. {cite:<18} {tag:<24} " + DIM(mech))
            if overflow:
                print("    " + DIM("floor 0; overflow -> " + "; ".join(overflow)))
        # connected authority (edges to non-DAG-member nodes), grouped by edge type
        by: dict[str, set] = {}
        for e in graph.neighbors(self.con, nid):
            other = e["dst"] if e["src"] == nid else e["src"]
            if other in members:
                continue
            by.setdefault(e["etype"], set()).add(other)
        if by:
            print(BOLD("\n  connected authority:"))
            for et in sorted(by):
                cites = sorted(graph.node(self.con, o)["citation"] for o in by[et])
                print(f"    {et:<16} " + DIM(", ".join(cites)))

    def do_node(self, arg):
        "node <id> — raw node fields + every edge touching it (applicability if a date is set)"
        nid = arg.strip()
        if not nid:
            print(RE("  usage: node <id>"))
            return
        n = graph.node(self.con, nid)
        if not n:
            print(RE(f"  no node '{nid}'"))
            return
        print(BOLD(f"{n['citation']} — {n['label']}  ({nid})"))
        win = f"{n['valid_from'] or '-'} .. {n['valid_to'] or '-'}"
        print(f"  type {n['ntype']}/{n['term_subtype'] or '-'}  tier {n['tier']} "
              f"({TIER.get(n['tier'], '?')})  validity {win}")
        if n["tags"]:
            print("  tags: " + DIM(", ".join(n["tags"])))
        if n["synthesis"]:
            print(f"  {n['synthesis']}")
        if self.as_of:
            ok = graph.applicable(self.con, nid, self.as_of)
            print(f"  as of {self.as_of}: " + (GR("IN FORCE") if ok else RE("NOT IN FORCE")))
        nb = graph.neighbors(self.con, nid)
        if nb:
            print(BOLD("  edges:"))
            for e in nb:
                print(f"    {e['etype']:<16} {e['src']} -> {e['dst']}  " + DIM(e["mechanism"] or ""))

    def do_quit(self, arg):
        "quit — exit the shell"
        print("bye")
        return True

    do_exit = do_quit

    def do_EOF(self, arg):
        print()
        return True

    # ---- cmd plumbing -------------------------------------------------------
    def emptyline(self):
        pass  # don't repeat the last command on a blank line

    def default(self, line):
        # anything that isn't a known command is treated as a question
        self.do_ask(line)


def main():
    shell = SubKShell()
    try:
        shell.cmdloop()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
