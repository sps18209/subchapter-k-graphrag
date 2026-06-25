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

CAPABILITIES = """\
================ SUBK ANALYZE — capabilities & limits ================
DOCTRINE WIRED:  Substantial economic effect only  (IRC 704(b); Treas. Reg. 1.704-1(b)).
                 Disguised sale, §1.701-2 anti-abuse, etc. are NOT wired yet.

HOW TO INPUT / WHERE FILES COME FROM
  • Folder (real matters): ~/subk-matters/<matter>/  (created for you; home dir because macOS
        blocks Terminal writes to ~/Downloads). Drop the partnership/operating agreement +
        capital-account statements there, then run with --matter/--folder.
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
  • Ingestion, the fact-frame, and the verified Layer-A bundle are 100% LOCAL.
  • The sandwich runs ONLY with --run, ANTHROPIC_API_KEY, AND SUBK_LLM_ZDR_CONFIRMED=1 (your
    attestation that the account is no-train / zero-data-retention; the pinned model supports ZDR).
  • MASKING: before anything is sent, client identifiers in the FACT items are replaced with local
    tokens ([ENTITY_1], [AMOUNT_1], [EIN_1], …). The model reasons over tokens and never sees raw
    identity; the map never leaves the machine and is un-masked locally for your display. Public
    LAW text is not masked. (SUBK_LLM_MASK=0 disables it.)
  • Layer B closure-checks the reply before you see it. Without the gates the tool stops at the
    local boundary — nothing leaves the machine.
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


def main():
    ap = argparse.ArgumentParser(description="Substantial-economic-effect analyzer (Phase 0: intake + contract)")
    ap.add_argument("--capabilities", action="store_true", help="print what this tool can and cannot do")
    ap.add_argument("--matter", help="matter name (uses ~/subk-matters/<slug>/)")
    ap.add_argument("--folder", help="folder of documents to ingest (read-only)")
    ap.add_argument("--facts", help="pasted facts (or @file)")
    ap.add_argument("--form", help="structured fact-frame as JSON (or @file)")
    ap.add_argument("--run", action="store_true",
                    help="run the reasoning sandwich (Layer A -> Anthropic -> Layer B); needs ANTHROPIC_API_KEY")
    args = ap.parse_args()

    if args.capabilities or not (args.matter or args.folder or args.facts or args.form):
        print(CAPABILITIES)
        if not args.capabilities:
            print("\nGive an input: --matter NAME | --folder PATH | --facts @file | --form JSON")
        return

    frame, ing, issue = build_frame(args)
    if frame is None:
        sys.exit("no input resolved — see --capabilities")

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

    if not (args.run and os.environ.get("ANTHROPIC_API_KEY")):
        print("\n================ LOCAL BOUNDARY ================")
        print("Nothing has left this machine. To run the reasoning sandwich (Layer A -> Anthropic ->")
        print(f"Layer B), set ANTHROPIC_API_KEY and add --run. The bundle above is EXACTLY what would")
        print(f"be sent to the pinned model ({subk_llm.PINNED_MODEL}); Layer B verifies the reply before")
        print("you ever see it. Nothing else leaves the machine.")
        print("================================================")
        return

    # Phase 1: run the sandwich. Rule 1.6 attestation gate — refuse until the operator confirms
    # the Anthropic account is no-train / zero-data-retention (code can't verify it; it must attest).
    if os.environ.get("SUBK_LLM_ZDR_CONFIRMED") != "1":
        print("\n================ BLOCKED (Rule 1.6) ================")
        print("Refusing to send client facts. Set SUBK_LLM_ZDR_CONFIRMED=1 to attest that your")
        print(f"Anthropic account is configured no-train / zero-data-retention and uses {subk_llm.PINNED_MODEL}")
        print("(which supports ZDR). Identifiers are masked regardless, but the attestation is required.")
        print("===================================================")
        return
    masking = "ON (identifiers masked before send)" if os.environ.get("SUBK_LLM_MASK", "1") != "0" else "OFF"
    print(f"\n*** --run: sending the MASKED bundle to {subk_llm.PINNED_MODEL}. Masking: {masking}. ***")
    envelope, masker = subk_llm.analyze(bundle, issue)
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
