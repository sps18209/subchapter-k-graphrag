#!/usr/bin/env python3
"""
assistant.py — a plain-English front door to the engine.

You type naturally ("how much basis is left if Joe started at 245k and took out 465k?")
and a router maps it to one of the engine's deterministic tools, runs it, and shows the
VERIFIED result. The model only routes + phrases the question — it never invents law or
numbers; every answer comes from retrieve.py / calculator.py / graph.py.

Routers (SUBK_ASSISTANT_PROVIDER):
  unset / "none"  rules     keyword + number/date heuristics. No model, no network, works now.
  "ollama"        local model via http://localhost:11434 (e.g. `ollama run llama3.2:3b`).
                  Nothing you type leaves the machine — best for matter facts and sharing.
  "openai"        OpenAI API (needs OPENAI_API_KEY). Sends your message out; see DEPLOY.md.

    python assistant.py            # interactive
    python assistant.py "is the QBI deduction still around in 2030?"   # one-shot
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import date

import graph
import retrieve
import calculator as calc
import cite_verify

CALC_FIELDS = [f.name for f in __import__("dataclasses").fields(calc.BasisInputs)]
_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

TOOLS = """Tools (return JSON {"tool": <name>, "args": {...}}):
- ask        args {"question": str, "as_of": "YYYY-MM-DD" or null}  — authority/explanation questions
- verify     args {"as_of": "YYYY-MM-DD"}                            — what is in force / superseded on a date
- compute    args {beginning_basis, cash_contributed, property_contributed_basis, liability_increase,
                   income_taxable, income_tax_exempt, depletion_excess, cash_distributed,
                   property_distributed_basis, liability_decrease, nondeductible, oil_gas_depletion, losses}
             (numbers; omit what isn't mentioned) — outside-basis calculation
- hubs       args {}                                                 — list the defined terms
- hub        args {"name": str}                                      — one term's formula + authority
- cite       args {"citation": str}                                  — check whether a citation is real/in-corpus
Pick exactly one tool. Extract dollar amounts and dates. Use COMPUTE ONLY when the user
gives or clearly wants a basis CALCULATION (there are dollar figures, or words like
compute/calculate/figure). A "what/which/why/how does ... work" question is ASK, not compute.

Examples:
  "what feeds a partner's outside basis?"            -> {"tool":"ask","args":{"question":"what feeds a partner's outside basis?"}}
  "explain disguised sales"                          -> {"tool":"ask","args":{"question":"explain disguised sales"}}
  "compute my basis: started 245k, distributed 465k" -> {"tool":"compute","args":{"beginning_basis":245000,"cash_distributed":465000}}
  "how much basis is left if beginning 100k loss 50k"-> {"tool":"compute","args":{"beginning_basis":100000,"losses":50000}}
  "what's in force as of 2026-06-01?"                -> {"tool":"verify","args":{"as_of":"2026-06-01"}}
  "is IRC 9999 a real cite?"                         -> {"tool":"cite","args":{"citation":"IRC 9999"}}"""


# ---- routers ------------------------------------------------------------------
def _rules_route(text: str) -> dict:
    t = text.lower()
    d = _DATE.search(text)
    cite = re.search(r"\b(IRC|Treas\.?\s*Reg|Rev\.?\s*Rul|Notice|P\.?L\.?)\b", text, re.I)
    if re.search(r"\b(compute|calculat|how much|ending basis|gain|suspend|losses?)\b", t) and re.search(r"\d", t):
        nums = {}  # rules can't reliably label fields; hand off to the guided prompt
        return {"tool": "compute", "args": nums}
    if re.search(r"\b(in force|currency|superseded|still good|as of)\b", t) and d:
        return {"tool": "verify", "args": {"as_of": d.group(1)}}
    if re.search(r"\b(list|what).{0,12}\b(terms|hubs|definitions)\b", t):
        return {"tool": "hubs", "args": {}}
    if cite and re.search(r"\b(real|exist|valid|check|verify)\b", t):
        return {"tool": "cite", "args": {"citation": text[cite.start():].strip()}}
    return {"tool": "ask", "args": {"question": text, "as_of": d.group(1) if d else None}}


def _chat(provider: str, system: str, user: str, json_mode: bool = True) -> str:
    if provider == "ollama":
        url = os.environ.get("OLLAMA_URL", "http://localhost:11434") + "/api/chat"
        payload = {"model": os.environ.get("SUBK_ASSISTANT_MODEL", "llama3.2:3b"),
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                   "stream": False, "options": {"temperature": 0}}
        if json_mode:
            payload["format"] = "json"
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())["message"]["content"]
    if provider == "openai":
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY not set")
        url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        payload = {"model": os.environ.get("SUBK_ASSISTANT_MODEL", "gpt-4o-mini"), "temperature": 0,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]
    raise ValueError(f"unknown provider {provider!r}")


def parse_intent(raw: str) -> dict | None:
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "tool" in obj:
            obj.setdefault("args", {})
            return obj
    except (json.JSONDecodeError, TypeError):
        pass
    return None


# prefix match (no trailing \b) so "compute"/"calculate"/"figuring" all hit
_COMPUTE_VERB = re.compile(r"\b(comput|calculat|figur|work out|run the number|how much|ending basis)", re.I)


def _guard(intent: dict, text: str) -> dict:
    """Correct the small model's most common mis-route: sending an explanation question
    to the calculator. Compute needs numbers or an explicit 'compute/calculate' ask —
    otherwise it's a question, so route to ask."""
    if intent.get("tool") == "compute":
        has_numbers = any(v for v in (intent.get("args") or {}).values())
        if not has_numbers and not re.search(r"\d", text) and not _COMPUTE_VERB.search(text):
            return {"tool": "ask", "args": {"question": text}}
    return intent


def route(text: str, provider: str | None) -> dict:
    if not provider or provider == "none":
        return _rules_route(text)
    try:
        intent = parse_intent(_chat(provider, "You are a precise tool router. " + TOOLS, text))
        return _guard(intent or _rules_route(text), text)
    except Exception as e:
        sys.stderr.write(f"[router fell back to rules: {e}]\n")
        return _rules_route(text)


# ---- tool execution (deterministic; the engine is the source of truth) --------
def _fmt_currency(rep: dict) -> str:
    out = [f"As of {rep['as_of']}:"]
    for label, key in [("IN FORCE", "in_force"), ("NOT YET", "not_yet_effective"),
                       ("REMOVED", "expired"), ("SUPERSEDED", "superseded")]:
        for cite, why in rep[key]:
            out.append(f"  [{label}] {cite} — {why}")
    return "\n".join(out)


def run(con, intent: dict, interactive: bool = True) -> str:
    tool = intent.get("tool", "ask")
    args = intent.get("args") or {}
    if tool == "verify":
        d = args.get("as_of")
        try:
            date.fromisoformat(d)
        except (TypeError, ValueError):
            return "I need a date like 2026-06-01 to check currency."
        return _fmt_currency(graph.currency_report(con, d))
    if tool == "compute":
        fields = {k: float(v) for k, v in args.items() if k in CALC_FIELDS and v is not None}
        if not fields and interactive:
            print("Let's compute outside basis. Enter dollar amounts; blank = 0.")
            for f in CALC_FIELDS:
                raw = input(f"  {f} [0]: ").strip().replace(",", "").replace("$", "")
                if raw:
                    fields[f] = float(raw)
        return calc.format_result(calc.compute_outside_basis(calc.BasisInputs(**fields)))
    if tool == "hubs":
        rows = con.execute("SELECT id,citation FROM node WHERE ntype='term' ORDER BY id").fetchall()
        return "Defined terms:\n" + "\n".join(f"  {nid:<22} {cite}" for nid, cite in rows)
    if tool == "hub":
        name = (args.get("name") or "").lower()
        row = con.execute("SELECT id FROM node WHERE ntype='term' AND "
                          "(lower(id) LIKE ? OR lower(citation) LIKE ? OR lower(label) LIKE ?)",
                          (f"%{name}%", f"%{name}%", f"%{name}%")).fetchone()
        if not row:
            return f"No term matching '{args.get('name')}'. Try `hubs`."
        rows, overflow, _ = retrieve._dag(con, row[0])
        lines = [f"{row[0]}:"] + [f"  {s:>2}. {cite:<16} {mech}" for s, _, _, cite, mech in rows]
        return "\n".join(lines) if rows else f"{row[0]} (no formula DAG)."
    if tool == "cite":
        v = cite_verify.verify(args.get("citation", ""), cite_verify.corpus_cites(con), cite_verify.get_verifier())
        return f"{v['citation']}: {v['status']} ({v['kind']}) — {v.get('note', v.get('source',''))}"
    # ask (default)
    q = args.get("question") or args.get("text") or ""
    return retrieve.assemble(con, retrieve.retrieve(con, q, as_of=args.get("as_of")))


DISCLAIMER = "Unverified seed for attorney review — not legal or tax advice."

HELP = """\
══════════════════════ subk-chat — what you can do ══════════════════════
Type in plain English. The model picks the query; the engine gives the answer.

  ASK about authority     →  what feeds a partner's outside basis?
  CHECK if law is current →  is the QBI deduction in force in 2030?
  COMPUTE outside basis   →  compute: started 245k, distributed 465k
  VERIFY a citation       →  is IRC 9999 a real cite?
  BROWSE the terms        →  list the terms   ·   explain disguised sale

Tips
  • say "compute" or include $ amounts to force the calculator
  • include a date like 2026-06-01 for "as of" currency questions
  • answers show a plain-English summary + the verified engine detail

Commands
  help  ?   show this map      quit  exit  q   leave
═════════════════════════════════════════════════════════════════════════"""


def _explain(provider: str, question: str, result: str) -> str:
    """Plain-English restatement of the engine's output. The model summarizes ONLY what the
    engine returned — it adds no law, cites, or numbers — so the verified detail below stays
    the source of truth. Returns '' on any failure (then only the technical output is shown)."""
    system = ("You restate a partnership-tax tool's output in plain English for a non-lawyer. "
              "Summarize ONLY what is in RESULT, in 2-3 short sentences. Do NOT add citations, "
              "numbers, dates, or legal conclusions that are not present in RESULT. No preamble.")
    try:
        return _chat(provider, system, f"QUESTION: {question}\n\nRESULT:\n{result}", json_mode=False).strip()
    except Exception:
        return ""


def respond(con, text: str, provider: str | None, interactive: bool = True) -> str:
    """Always route through the engine; when a model is configured (and SUBK_ASSISTANT_EXPLAIN
    isn't 0), prepend a plain-English summary above the verified engine output."""
    detail = run(con, route(text, provider), interactive=interactive)
    if provider and provider != "none" and os.environ.get("SUBK_ASSISTANT_EXPLAIN", "1") != "0":
        summary = _explain(provider, text, detail)
        if summary:
            return ("PLAIN ENGLISH (model summary — the verified detail is below):\n  "
                    + summary.replace("\n", "\n  ")
                    + "\n\nVERIFIED DETAIL (from the deterministic engine):\n" + detail)
    return detail


def main():
    provider = os.environ.get("SUBK_ASSISTANT_PROVIDER")
    con = graph.build(":memory:")
    one_shot = " ".join(sys.argv[1:]).strip()
    mode = provider if provider and provider != "none" else "rules (no model)"
    if one_shot:
        print(respond(con, one_shot, provider, interactive=False))
        print("\n" + DISCLAIMER)
        return
    print(HELP)
    print(f"\nRouting: {mode}.  {DISCLAIMER}\n")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text.lower() in ("quit", "exit", "q"):
            break
        if text.lower() in ("help", "?", "menu", "commands", "map"):
            print(HELP)
            continue
        print(respond(con, text, provider))
        print()


if __name__ == "__main__":
    main()
