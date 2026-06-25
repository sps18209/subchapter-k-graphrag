#!/usr/bin/env python3
"""
subk_analyze.py — orchestrator for the substantial-economic-effect analyzer (Phase 0).

Principle (same as the rest of this project): the model PROPOSES, deterministic code GATES.
Phase 0 builds and proves the RELIABILITY CONTRACT — intake, scope, sufficiency, and the
verified Layer-A authority bundle — and STOPS at the local boundary. The reasoning step
(Layer A -> Anthropic -> Layer B) is intentionally not executed yet: the Layer-B verifier that
makes sending data safe is Phase 1, so this phase never sends anything out.

    python subk_analyze.py --capabilities
    python subk_analyze.py --matter "Smith Partners" --folder ~/subk-matters/smith-partners
    python subk_analyze.py --facts @notes.txt
    python subk_analyze.py --form '{"allocation_at_issue":"99% of depreciation to A","qualified_income_offset":true}'
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import subk_see
import subk_intake
import subk_llm
import redact

CAPABILITIES = """\
================ SUBK ANALYZE — capabilities & limits ================
DOCTRINE WIRED:  Substantial economic effect only  (IRC 704(b); Treas. Reg. 1.704-1(b)).
                 Disguised sale, §1.701-2 anti-abuse, etc. are NOT wired yet.

HOW TO INPUT / WHERE FILES COME FROM
  • Guided + ROLE-BASED (recommended): --interview asks each party's real name (kept LOCAL, scrubbed
        everywhere before send) and what they ARE in the deal; the analysis represents each party by
        ROLE — "the contributing partner", never a name or a code. Or: --parties "John Doe:contributing".
  • Folder (real matters): ~/subk-matters/<matter>/  (created for you; home dir because macOS
        blocks Terminal writes to ~/Downloads). Drop the agreement + capital-account statements there.
  • Light path: --facts (paste/notes) or --form (structured JSON) for hypotheticals & study.
  Source files are READ-ONLY — never modified or deleted.

WHAT CAN BE INGESTED
  • File types: .txt, .md, searchable .pdf (needs pdfplumber), .docx (needs python-docx).
  • Subject:    §704(b) allocation / economic-effect questions.

WHAT CANNOT BE INGESTED / IS DECLINED  (so you know the edges)
  • Other doctrines (declined as out of scope until wired).
  • Scanned/image-only PDFs — no OCR/layout backend is wired; reported as skipped, never guessed.
  • Encrypted / unreadable files — reported as skipped with the reason.
  • A matter with no agreement provisions — economic effect lives in the agreement; the tool
    reports which factors it CANNOT reach instead of inventing them.

WHAT IT WILL NOT DO
  • It does not reach the ultimate legal conclusion. It produces a factor-by-factor work-up;
    whether the allocation HAS substantial economic effect is a conclusion of law you make.

CONFIDENTIALITY BOUNDARY (Rule 1.6)
  • ANONYMIZE AT SOURCE: enter parties as short codes (--interview / --parties), so no real name
    ever enters the tool — local OR cloud. This is the primary defense; masking below is a backstop.
  • Ingestion, the fact-frame, and the verified Layer-A bundle are 100% LOCAL.
  • The sandwich runs ONLY with --run, ANTHROPIC_API_KEY, AND SUBK_LLM_ZDR_CONFIRMED=1 (your
    attestation that the account is no-train / zero-data-retention; the pinned model supports ZDR).
  • MASKING: before anything is sent, client identifiers in the FACT items are replaced with local
    tokens ([ENTITY_1], [AMOUNT_1], [EIN_1], …). The model reasons over tokens and never sees raw
    identity; the map never leaves the machine and is un-masked locally for your display. Public
    LAW text is not masked. (SUBK_LLM_MASK=0 disables it.)
  • Layer B closure-checks the reply before you see it. Without the gates the tool stops at the
    local boundary — nothing leaves the machine.
  • ONE EXIT, FAIL-CLOSED: all sends pass a single point that refuses if any registered name
    survived redaction; every send is recorded to a local egress log (sha256 of the scrubbed
    payload + a roles-only redaction summary, never names) at ~/subk-matters/.egress-log.jsonl.
====================================================================="""


def _load_arg(val: str) -> str:
    """Allow @file to read a value from a file."""
    if val and val.startswith("@"):
        with open(os.path.expanduser(val[1:]), "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    return val or ""


def verify_authority() -> dict:
    """Layer A: confirm the SEE reg section is real and current against live eCFR. Degrades to
    'unverified (offline)' on any failure — never blocks."""
    try:
        import cite_verify
        hit = cite_verify.OnlineVerifier().check("Treas. Reg. 1.704-1", "regulation") or {}
        return {"cite": subk_see.ROOT_CITE, "status": hit.get("status", "unverified"),
                "as_of": hit.get("as_of"), "last_amended": hit.get("last_amended")}
    except Exception:
        return {"cite": subk_see.ROOT_CITE, "status": "unverified (offline)"}


def build_frame(args) -> tuple[dict, dict, str]:
    """Return (frame, ingest_report, issue_text) from whichever input door was used."""
    if args.form:
        form = json.loads(_load_arg(args.form))
        frame = subk_intake.frame_from_form(form)
        return frame, {"report": [], "facts": json.dumps(form)}, str(form)
    if args.facts:
        text = _load_arg(args.facts)
        return subk_intake.detect_provisions(text, source="pasted facts"), {"report": [], "facts": text}, text
    # folder path
    folder = args.folder or (subk_intake.matter_dir(args.matter) if args.matter else None)
    if not folder:
        return None, None, ""
    ing = subk_intake.ingest_folder(folder)
    frame = subk_intake.detect_provisions(ing["facts"], source="matter folder")
    return frame, ing, ing["facts"]


def _parties_to_roster(pairs: list, redactor) -> list:
    """pairs = [(raw, role)]. Represent each party by its FUNCTIONAL ROLE (what it truly is in the
    deal) — never a name or a code. Any real NAME is registered in the redactor mapped to its role
    label, so the name is scrubbed to its role everywhere before send. Returns the role labels."""
    used, labels = set(), []
    for raw, role in pairs:
        label = subk_intake.role_label(role, used)
        if raw and redact.looks_like_name(raw):
            redactor.add_name(raw, code=label)      # John Doe -> 'Contributing partner'
        labels.append(label)
    return labels


def _interview(redactor) -> dict:
    """Guided intake. Collects each party's REAL name (kept LOCAL, scrubbed before send) and what it
    IS in the deal; the analysis represents each party by its ROLE — never a name or code."""
    print("================ GUIDED INTAKE ================")
    print("Enter each party's REAL name (stays on THIS machine) and what they ARE in the deal. The")
    print("name is scrubbed everywhere before send; the analysis represents each party by ROLE")
    print("(e.g. 'the contributing partner') — never a name or a code.\n")
    try:
        n = int((input("How many parties are involved in this allocation issue? ").strip() or "0"))
    except ValueError:
        n = 0
    pairs = []
    for i in range(max(n, 0)):
        raw = input(f"  Party {i + 1} full name (kept local) — or Enter if unknown: ").strip()
        role = input(f"  Party {i + 1} role — what they ARE (contributing / service / managing partner; "
                     "or employee, plaintiff, …): ").strip()
        pairs.append((raw, role))
    labels = _parties_to_roster(pairs, redactor)
    for (raw, _), label in zip(pairs, labels):
        lead = f"'{raw}' -> " if (raw and redact.looks_like_name(raw)) else ""
        print(f"    {lead}represented in the analysis as: {label}")

    form = {}
    if labels:
        form["parties"] = "; ".join(labels)
    print("\nNow the facts — refer to parties by ROLE (e.g. 'the contributing partner').")
    form["allocation_at_issue"] = input(
        "  Allocation being tested (e.g. '99% of depreciation to the contributing partner'): ").strip()

    def yn(q):
        a = input(f"  {q} [y/N/? unknown]: ").strip().lower()
        return True if a.startswith("y") else (None if a.startswith("?") else False if a.startswith("n") else None)

    for field, q in [
        ("capital_account_maintenance", "Does the agreement maintain capital accounts per Reg. 1.704-1(b)(2)(iv)?"),
        ("liquidation_per_positive_ca", "Are liquidating distributions made per positive capital accounts?"),
        ("deficit_restoration_obligation", "Is there an UNCONDITIONAL deficit-restoration obligation?"),
        ("qualified_income_offset", "Does the agreement contain a qualified income offset?"),
    ]:
        v = yn(q)
        if v is not None:
            form[field] = v
    for field, q in [("capital_account_balances", "Capital-account balances (use codes; vague amounts OK)"),
                     ("tax_motivation", "Any facts suggesting the allocation is tax-motivated?")]:
        a = input(f"  {q} [optional]: ").strip()
        if a:
            form[field] = a
    print("===================================================================\n")
    return form


def main():
    ap = argparse.ArgumentParser(description="Substantial-economic-effect analyzer (Phase 0: intake + contract)")
    ap.add_argument("--capabilities", action="store_true", help="print what this tool can and cannot do")
    ap.add_argument("--matter", help="matter name (uses ~/subk-matters/<slug>/)")
    ap.add_argument("--folder", help="folder of documents to ingest (read-only)")
    ap.add_argument("--facts", help="pasted facts (or @file)")
    ap.add_argument("--form", help="structured fact-frame as JSON (or @file)")
    ap.add_argument("--interview", action="store_true",
                    help="guided, ANONYMIZED intake — asks for party codes (never real names) + the facts")
    ap.add_argument("--parties", help="anonymized roster, e.g. 'RoSm:contributing, ToJo:service'")
    ap.add_argument("--run", action="store_true",
                    help="run the reasoning sandwich (Layer A -> model -> Layer B); see --capabilities")
    args = ap.parse_args()

    if args.capabilities or not (args.matter or args.folder or args.facts or args.form or args.interview):
        print(CAPABILITIES)
        if not args.capabilities:
            print("\nGive an input: --interview (guided, anonymized) | --matter NAME | --folder PATH | "
                  "--facts @file | --form JSON")
        return

    redactor = redact.Redactor()
    if args.interview:
        form = _interview(redactor)
        frame = subk_intake.frame_from_form(form)
        ing = {"report": [], "facts": json.dumps(form)}
        issue = (form.get("allocation_at_issue", "") + " " + form.get("parties", "")).strip()
    else:
        frame, ing, issue = build_frame(args)
        if frame is None:
            sys.exit("no input resolved — see --capabilities")
        if args.parties:
            parsed = subk_intake.parse_parties(args.parties)
            roster = "; ".join(_parties_to_roster([(p["code"], p["role"]) for p in parsed], redactor))
            frame["fields"]["parties"] = {"value": roster, "quote": roster, "source": "attorney input"}

    scope = subk_intake.scope_check(issue)
    ready = subk_see.readiness(frame)
    auth = verify_authority()

    print("================ RELIABILITY MANIFEST (this run) ================")
    # what came in
    if ing.get("report"):
        print("INGESTED:")
        for r in ing["report"]:
            print(f"  {r['status']:<48} {r['file']}  ({r['chars']} chars via {r['backend']})")
    print(f"\nSCOPE: {'IN SCOPE' if scope['in_scope'] else 'OUT OF SCOPE'} — {scope['reason']}")
    if scope["signals"]:
        print("  signals:", ", ".join(scope["signals"]))

    print(f"\nAUTHORITY (Layer A): {auth['cite']} — {auth['status']}"
          + (f", current as of {auth['as_of']}" if auth.get("as_of") else "")
          + (f", last amended {auth['last_amended']}" if auth.get("last_amended") else ""))

    print("\nFACTS DETECTED (each traceable to its source quote):")
    for f, v in frame["fields"].items():
        if v["value"] is not None:
            q = (v["quote"] or "")[:70]
            print(f"  ✓ {f:<32} [{v['source']}] {q}")

    print(f"\nREADINESS: {'READY to analyze' if ready['ready'] else 'NOT READY'}")
    if ready["missing_minimum"]:
        print("  missing the minimum:", ", ".join(ready["missing_minimum"]))
    print("  economic-effect paths reachable:", ", ".join(ready["economic_effect_paths_reachable"]) or "none")
    if ready["factors_blocked"]:
        print("  factors the tool CANNOT reach from these facts:")
        for b in ready["factors_blocked"]:
            print(f"    {b['id']:<14} needs: {', '.join(b['missing'])}")

    # Layer A: the verified bundle (deterministic; this is exactly what the model may use).
    bundle = subk_llm.build_bundle(frame, auth)
    print("\n================ LAYER A — VERIFIED BUNDLE (the only material the model may use) ================")
    print(f"  {len(bundle['items'])} items · cache key {subk_llm.bundle_key(bundle)}")
    for it in bundle["items"]:
        print(f"  [{it['id']:<22}] {it['text'][:88]}")

    if not ready["ready"]:
        print("\nNot ready — supply the missing facts above before running the analysis.")
        return

    prov = subk_llm.provider()
    local = prov == "ollama"
    if not (args.run and (local or os.environ.get("ANTHROPIC_API_KEY"))):
        print("\n================ LOCAL BOUNDARY ================")
        print("Nothing has left this machine. To run the reasoning sandwich (Layer A -> model -> Layer B):")
        print(f"  • CLOUD  : set ANTHROPIC_API_KEY + SUBK_LLM_ZDR_CONFIRMED=1, then --run (pinned {subk_llm.PINNED_MODEL},")
        print("             identifiers masked, narrow-retention/ZDR account).")
        print("  • LOCAL  : set SUBK_LLM_PROVIDER=ollama, then --run — runs entirely on this machine,")
        print("             no key, no ZDR, nothing leaves the box.")
        print("The bundle above is EXACTLY what a run would reason over; Layer B verifies the reply either way.")
        print("================================================")
        return

    # Cloud only: Rule 1.6 attestation gate (code can't verify retention; the operator must attest).
    if not local and os.environ.get("SUBK_LLM_ZDR_CONFIRMED") != "1":
        print("\n================ BLOCKED (Rule 1.6) ================")
        print("Refusing to send client facts to the cloud. Either set SUBK_LLM_ZDR_CONFIRMED=1 to attest")
        print(f"your Anthropic account is no-train / zero-data-retention (the pinned {subk_llm.PINNED_MODEL} supports")
        print("ZDR), OR run fully local with SUBK_LLM_PROVIDER=ollama (no attestation needed).")
        print("===================================================")
        return

    # Pre-send guard: declared names are already scrubbed by the redactor; surface any UN-declared
    # names in the payload (honorifics / captions / signature blocks) for you to label first.
    payload = "\n".join(it["text"] for it in bundle["items"] if it["kind"] in ("fact", "cite"))
    candidates = redact.scan_candidates(payload, redactor)
    if candidates:
        if sys.stdin.isatty():
            print("\nPossible client names in what would be sent — label each (Enter = leave as-is):")
            for name in candidates:
                ans = input(f"  '{name}' -> code (Enter to ignore): ").strip()
                if ans:
                    redactor.add(name, ans)
        else:
            print("\n================ BLOCKED — un-rostered names ================")
            print("These look like client names in the payload and aren't in your roster:")
            print("  " + ", ".join(candidates))
            print("Re-run with --interview to label them. Nothing was sent.")
            print("============================================================")
            return

    if local:
        print(f"\n*** --run LOCAL: {os.environ.get('SUBK_LLM_OLLAMA_MODEL', 'llama3.2:3b')} via Ollama — nothing")
        print("    leaves this machine. (Smaller local model: lower quality, but Layer B still rejects ungrounded output.) ***")
    else:
        masking = "ON" if os.environ.get("SUBK_LLM_MASK", "1") != "0" else "OFF"
        print(f"\n*** --run CLOUD: sending the REDACTED + masked bundle to {subk_llm.PINNED_MODEL}. Masking: {masking}. ***")
    try:
        envelope, masker = subk_llm.analyze(bundle, issue, redactor=redactor)
    except subk_llm.EgressBlocked as e:
        print("\n================ BLOCKED — egress invariant (fail-closed) ================")
        print(f"  {e}. Nothing was sent.")
        print("  A registered identifier would have left the machine. Re-run --interview so the")
        print("  name is mapped to a role and scrubbed everywhere.")
        print("=========================================================================")
        return
    if not envelope:
        sys.exit("the model returned nothing (check ANTHROPIC_API_KEY and `pip install anthropic`).")
    v = subk_llm.layer_b_verify(envelope, bundle["ids"])
    for p in v["propositions"]:          # un-mask locally for display (the map never left the machine)
        p["text"] = masker.unmask(p["text"])
    for a in v["augmentations"]:
        a["text"], a["source"] = masker.unmask(a["text"]), masker.unmask(a["source"])
    v["ultimate_question"] = masker.unmask(v["ultimate_question"])
    v["gaps"] = [masker.unmask(g) for g in v["gaps"]]
    head = "CLOSED ✓ (all legal content traces to the verified bundle)" if v["closed"] \
        else "OPEN — review the flagged items below"
    print(f"\n================ VERIFIED ANALYSIS — Layer B: {head} ================")
    for p in v["propositions"]:
        mark = "✓" if p["verdict"] == "ok" else "✗ REJECTED"
        print(f"  [{mark}] {p['text']}")
        for prob in p["problems"]:
            print(f"        ! {prob}")
    if v["augmentations"]:
        print("  -- non-legal context (segregated, flagged for review) --")
        for a in v["augmentations"]:
            mark = "✓" if a["verdict"] == "ok" else "✗ REJECTED"
            print(f"  [{mark}] ({a['category']}) {a['text']}  [source: {a['source']}]")
            for prob in a["problems"]:
                print(f"        ! {prob}")
    for g in v["gaps"]:
        print("  gap:", g)
    print(f"\n  ULTIMATE QUESTION (yours to decide): {v['ultimate_question']}")
    print(f"  {v['conclusion']}")


if __name__ == "__main__":
    main()
