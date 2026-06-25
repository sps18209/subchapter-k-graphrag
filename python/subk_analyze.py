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
  • Ingestion, the fact-frame, and the verified factor tree are 100% LOCAL.
  • The reasoning step would send the fact-frame + verified law to Anthropic. In this phase it
    is GATED OFF: nothing leaves the machine. The tool stops at the boundary and shows what it
    WOULD send once Layer B is built.
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

    print("\n================ LOCAL BOUNDARY ================")
    print("Nothing has left this machine. The reasoning step (Layer A -> Anthropic -> Layer B) is")
    print("Phase 1 and is intentionally not executed: the Layer-B verifier that makes it safe to")
    print("send the fact-frame out isn't built yet. What WOULD be sent, once it is:")
    print(f"  • {len([1 for v in frame['fields'].values() if v['value'] is not None])} detected facts (above)")
    print(f"  • the verified factor tree for {subk_see.DOCTRINE} ({len(subk_see.FACTORS)} factors, rooted at {auth['cite']})")
    print("================================================")


if __name__ == "__main__":
    main()
