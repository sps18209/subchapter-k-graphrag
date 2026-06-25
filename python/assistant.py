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
import horizon

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
- source     args {"citation": str}                                  — fetch the ACTUAL current text of a reg/statute/ruling from the primary source
- horizon    args {"terms": str or null}                             — scan PROPOSED federal tax bills in Congress (NOT law/authority; pending only)
Pick exactly one tool. Extract dollar amounts and dates. Use COMPUTE ONLY when the user
gives or clearly wants a basis CALCULATION (there are dollar figures, or words like
compute/calculate/figure). A "what/which/why/how does ... work" question is ASK, not compute.
Use SOURCE when the user wants to READ or QUOTE the authority itself ("what does X say",
"pull up the text of X", "show me the language of X"); use CITE only to check if it's real.
Use HORIZON for PENDING / PROPOSED legislation ("any bills on X", "what's coming in Congress",
"proposed legislation") — these are bills, not enacted law.

Examples:
  "what feeds a partner's outside basis?"            -> {"tool":"ask","args":{"question":"what feeds a partner's outside basis?"}}
  "explain disguised sales"                          -> {"tool":"ask","args":{"question":"explain disguised sales"}}
  "compute my basis: started 245k, distributed 465k" -> {"tool":"compute","args":{"beginning_basis":245000,"cash_distributed":465000}}
  "how much basis is left if beginning 100k loss 50k"-> {"tool":"compute","args":{"beginning_basis":100000,"losses":50000}}
  "what's in force as of 2026-06-01?"                -> {"tool":"verify","args":{"as_of":"2026-06-01"}}
  "is IRC 9999 a real cite?"                         -> {"tool":"cite","args":{"citation":"IRC 9999"}}
  "what does Treas. Reg. 1.704-2 actually say?"      -> {"tool":"source","args":{"citation":"Treas. Reg. 1.704-2"}}
  "pull up the text of IRC 704"                      -> {"tool":"source","args":{"citation":"IRC 704"}}
  "any pending bills on carried interest?"           -> {"tool":"horizon","args":{"terms":"carried interest"}}
  "what tax legislation is coming for partnerships?" -> {"tool":"horizon","args":{}}"""


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
    if re.search(r"\b(pending|proposed|legislation|legislative|horizon|in congress|bills?\s+in\b)\b", t):
        topic = re.search(r"\b(?:on|about|for|regarding)\s+(.+?)\s*\??$", text.strip(), re.I)
        return {"tool": "horizon", "args": {"terms": topic.group(1).strip()} if topic else {}}
    if cite and re.search(r"\b(real|exist|valid|check|verify)\b", t):
        return {"tool": "cite", "args": {"citation": text[cite.start():].strip()}}
    if re.search(r"\b(text of|language of|quote|full text|actual text|pull up|read me|show me)\b", t) \
            or re.search(r"what does .{0,40}\b(say|provide|state|require)\b", t):
        found = cite_verify.extract_citations(text)
        if not found:
            sec = re.search(r"\bsection\s+(\d+[A-Za-z\-.]*)", text, re.I)
            if sec:
                found = ["IRC " + sec.group(1)]
        if found:
            return {"tool": "source", "args": {"citation": found[0]}}
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


def _render_source(citation: str, max_chars: int = 900) -> str:
    """Fetch and show the actual current text of an authority from its primary source."""
    citation = (citation or "").strip()
    if not citation:
        return "Tell me which authority to pull up, e.g. `text of Treas. Reg. 1.704-2`."
    hit = cite_verify.OnlineVerifier().text(citation)   # source lookup is inherently online
    if not hit:
        return f"Couldn't fetch a primary source for '{citation}'. Check the citation format."
    head = f"{citation} — {hit['source']}"
    if hit.get("as_of"):
        head += f", current as of {hit['as_of']}"
    if hit.get("last_amended"):
        head += f", last amended {hit['last_amended']}"
    body = (hit.get("text") or "").strip()
    if not body:
        return (f"{head}\n  Full text isn't cleanly extractable here — read the authoritative "
                f"source:\n  {hit.get('url', '')}")
    excerpt = body[:max_chars]
    tail = "" if len(body) <= max_chars else "\n  … [excerpt — full current text at the link above]"
    return f"{head}\n  {hit.get('url', '')}\n\n{excerpt}{tail}"


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
        line = f"{v['citation']}: {v['status']} ({v['kind']})"
        if v.get("source"):
            line += f" — {v['source']}"
        if v.get("as_of"):
            line += f", current as of {v['as_of']}"
        if v.get("last_amended"):
            line += f", last amended {v['last_amended']}"
        if v.get("url"):
            line += f"\n  {v['url']}"
        if v.get("note"):
            line += f"\n  {v['note']}"
        live = v.get("live")
        if live:
            line += f"\n  live source check: {live['status']} via {live.get('source')}"
            if live.get("as_of"):
                line += f" (current as of {live['as_of']})"
            if live.get("last_amended"):
                line += f", last amended {live['last_amended']}"
            if live.get("url"):
                line += f"\n    {live['url']}"
        return line
    if tool == "source":
        return _render_source(args.get("citation", ""))
    if tool == "horizon":
        terms = args.get("terms")
        terms = ['"' + terms.strip() + '"'] if isinstance(terms, str) and terms.strip() else None
        try:
            return horizon.format_scan(horizon.scan(terms=terms))
        except Exception as e:
            return (f"Couldn't reach the legislation source ({e}).\n"
                    + horizon.DISCLAIMER)
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
  READ the actual law     →  what does Treas. Reg. 1.704-2 say?
  SCAN proposed bills     →  any pending bills on carried interest?  (NOT law)
  BROWSE the terms        →  list the terms   ·   explain disguised sale

Tips
  • say "compute" or include $ amounts to force the calculator
  • include a date like 2026-06-01 for "as of" currency questions
  • answers show a plain-English summary (grounded in live primary law) + verified detail

Commands
  help  ?   show this map      quit  exit  q   leave
═════════════════════════════════════════════════════════════════════════"""


def _live_grounding(detail: str, k: int = 2, max_chars: int = 1100) -> str:
    """Fetch the ACTUAL current text of the top authorities the engine cited, so the plain-English
    summary is grounded in real primary law (eCFR regs / US Code statutes), not the model's memory.
    Returns a context block (empty if nothing fetchable). Best-effort; network failures are skipped."""
    v = cite_verify.OnlineVerifier()
    blocks, used = [], 0
    for c in cite_verify.extract_citations(detail):
        if used >= k:
            break
        kind = cite_verify.classify(c)
        if kind not in ("regulation", "statute"):   # rulings/cases have no clean live text
            continue
        try:
            hit = v.text(c, kind)
        except Exception:
            hit = None
        body = (hit or {}).get("text", "").strip()
        if not body:
            continue
        stamp = f" (current as of {hit['as_of']})" if hit.get("as_of") else ""
        blocks.append(f"[{c} — {hit['source']}{stamp}]\n{body[:max_chars]}")
        used += 1
    return "\n\n".join(blocks)


def _explain(provider: str, question: str, result: str, grounding: str = "") -> str:
    """Plain-English explanation of the engine's output. The model may use ONLY the engine RESULT
    and the PRIMARY SOURCE TEXT (real current law fetched live) — never its own memory of the law —
    so the verified detail below stays the source of truth. Returns '' on any failure."""
    if grounding:
        system = ("You explain a partnership-tax tool's output in plain English for a non-lawyer, "
                  "grounded in the actual current law provided. Use ONLY the RESULT and the PRIMARY "
                  "SOURCE TEXT (real, current statutory/regulatory language). Base your 2-4 sentence "
                  "explanation on these materials only; you may paraphrase the source text, but do "
                  "NOT add law, numbers, or conclusions not supported by them. No preamble.")
        user = f"QUESTION: {question}\n\nRESULT:\n{result}\n\nPRIMARY SOURCE TEXT (authoritative):\n{grounding}"
    else:
        system = ("You restate a partnership-tax tool's output in plain English for a non-lawyer. "
                  "Summarize ONLY what is in RESULT, in 2-3 short sentences. Do NOT add citations, "
                  "numbers, dates, or legal conclusions that are not present in RESULT. No preamble.")
        user = f"QUESTION: {question}\n\nRESULT:\n{result}"
    try:
        return _chat(provider, system, user, json_mode=False).strip()
    except Exception:
        return ""


def respond(con, text: str, provider: str | None, interactive: bool = True) -> str:
    """Always route through the engine; when a model is configured (and SUBK_ASSISTANT_EXPLAIN
    isn't 0), prepend a plain-English summary GROUNDED IN THE LIVE PRIMARY SOURCES the engine
    cited. Disable grounding (faster, no network) with SUBK_EXPLAIN_GROUNDING=0."""
    intent = route(text, provider)
    detail = run(con, intent, interactive=interactive)
    # horizon output is self-labeled "NOT law" — don't let the model paraphrase that framing away.
    if intent.get("tool") != "horizon" and provider and provider != "none" \
            and os.environ.get("SUBK_ASSISTANT_EXPLAIN", "1") != "0":
        grounding = "" if os.environ.get("SUBK_EXPLAIN_GROUNDING", "1") == "0" else _live_grounding(detail)
        summary = _explain(provider, text, detail, grounding)
        if summary:
            tag = "grounded in live primary sources" if grounding else "model summary"
            return (f"PLAIN ENGLISH ({tag} — the verified detail is below):\n  "
                    + summary.replace("\n", "\n  ")
                    + "\n\nVERIFIED DETAIL (from the deterministic engine):\n" + detail)
    return detail


def _set_title(name: str) -> None:
    """Label the terminal tab/window (xterm / iTerm / Terminal.app). Set SUBK_TITLE to rename."""
    sys.stdout.write(f"\033]0;{name}\007")
    sys.stdout.flush()


def main():
    provider = os.environ.get("SUBK_ASSISTANT_PROVIDER")
    con = graph.build(":memory:")
    one_shot = " ".join(sys.argv[1:]).strip()
    mode = provider if provider and provider != "none" else "rules (no model)"
    if one_shot:
        print(respond(con, one_shot, provider, interactive=False))
        print("\n" + DISCLAIMER)
        return
    _set_title(os.environ.get("SUBK_TITLE", "Subchapter K"))
    print(HELP)
    print(f"\nRouting: {mode}.  {DISCLAIMER}")
    print("Ask your first question below — plain English — or type `help` for the map.\n")
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
