#!/usr/bin/env python3
"""
cite_verify.py — citation verification gate.

"Never emit an unverified cite as good law." This classifies and verifies legal
citations so the enrichment layer (and any external input) can be checked before a
citation is trusted. Pure stdlib for the structural + corpus check; an optional online
provider (CourtListener) confirms case citations.

A citation gets one of:
  in_corpus          present in the attorney-curated graph — the strongest signal here
  verified_external  confirmed to exist by an online source (cases, via CourtListener)
  well_formed        valid citation FORMAT but not in the corpus — verify against primary source
  unrecognized       matches no known citation format — likely an error / hallucination
  not_found          a well-formed case the online source could not find

Used by enrich.py to flag citations a model draft references. CLI:
  python cite_verify.py "IRC 704(d)"
  python cite_verify.py --text "see Rev. Rul. 2024-14 and the made-up IRC 9999(z)"
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

# Classification patterns for the citation TYPES this corpus uses.
_PATTERNS = [
    ("statute", re.compile(r"^(?:IRC|I\.R\.C\.|§)\s*§?\s*\d+[A-Za-z]?(?:\([^)]+\))*$", re.I)),
    ("regulation", re.compile(r"^(?:Prop\.?\s*)?Treas\.?\s*Reg\.?\s*[\d.]+", re.I)),
    ("regulation", re.compile(r"^\d+\s*CFR\s*[\d.]+", re.I)),
    ("ruling", re.compile(r"^(?:Rev\.?\s*Rul\.?|Rev\.?\s*Proc\.?|Notice|Announcement|T\.?D\.?)\s*\d{2,4}", re.I)),
    ("public_law", re.compile(r"^(?:P\.?L\.?|Pub\.?\s*L\.?)\s*\d+-\d+", re.I)),
    ("federal_register", re.compile(r"^\d+\s*FR\s*\d+", re.I)),
]

# Loose extractor: pull structured citations out of prose (for checking model drafts).
_EXTRACT = re.compile(
    r"IRC\s*§?\s*\d+[A-Za-z]?(?:\([^)]+\))*"
    r"|(?:Prop\.?\s*)?Treas\.?\s*Reg\.?\s*[\d.]+(?:\([^)]+\))*"
    r"|Rev\.?\s*Rul\.?\s*\d{4}-\d+"
    r"|Rev\.?\s*Proc\.?\s*\d{4}-\d+"
    r"|Notice\s*\d{4}-\d+"
    r"|P\.?L\.?\s*\d+-\d+"
    r"|\d+\s*FR\s*\d+"
    r"|T\.?D\.?\s*\d+",
    re.I,
)


def classify(citation: str) -> str:
    c = citation.strip()
    for kind, rx in _PATTERNS:
        if rx.match(c):
            return kind
    if re.search(r"\bv\.\s", c):  # "Commissioner v. Culbertson"
        return "case"
    return "unknown"


def extract_citations(text: str) -> list[str]:
    seen, out = set(), []
    for m in _EXTRACT.finditer(text or ""):
        c = re.sub(r"\s+", " ", m.group(0)).strip()
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def verify(citation: str, corpus_cites: set, provider=None) -> dict:
    c = citation.strip()
    kind = classify(c)
    if c in corpus_cites:
        return {"citation": c, "kind": kind, "status": "in_corpus",
                "note": "present in the attorney-curated graph"}
    if provider is not None and kind == "case":
        ok = provider.exists(c)
        return {"citation": c, "kind": kind,
                "status": "verified_external" if ok else "not_found", "source": provider.name}
    if kind != "unknown":
        return {"citation": c, "kind": kind, "status": "well_formed",
                "note": "valid format, not in corpus — verify against primary source"}
    return {"citation": c, "kind": "unknown", "status": "unrecognized",
            "note": "matches no known citation format — possible error"}


def verify_text(text: str, corpus_cites: set, provider=None) -> list[dict]:
    return [verify(c, corpus_cites, provider) for c in extract_citations(text)]


class CourtListenerVerifier:
    """Optional online check for CASE citations via the free CourtListener API."""
    name = "courtlistener"
    URL = "https://www.courtlistener.com/api/rest/v4/citation-lookup/"

    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("COURTLISTENER_TOKEN")

    def exists(self, citation: str) -> bool:
        try:
            body = json.dumps({"text": citation}).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            if self.token:
                headers["Authorization"] = "Token " + self.token
            req = urllib.request.Request(self.URL, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            return any(item.get("clusters") for item in data)
        except Exception:
            return False


def get_verifier(provider: str | None = None):
    provider = provider if provider is not None else os.environ.get("SUBK_CITE_PROVIDER")
    if not provider or provider == "none":
        return None
    if provider == "courtlistener":
        return CourtListenerVerifier()
    raise ValueError(f"unknown SUBK_CITE_PROVIDER: {provider!r} (use none|courtlistener)")


def corpus_cites(con) -> set:
    return {r[0] for r in con.execute("SELECT citation FROM node")}


if __name__ == "__main__":
    import argparse
    import graph
    ap = argparse.ArgumentParser(description="Verify legal citations against the corpus + format")
    ap.add_argument("citation", nargs="?")
    ap.add_argument("--text", help="extract and verify every citation found in this text")
    args = ap.parse_args()
    con = graph.build(":memory:")
    cites = corpus_cites(con)
    prov = get_verifier()
    if args.text:
        print(json.dumps(verify_text(args.text, cites, prov), indent=2))
    elif args.citation:
        print(json.dumps(verify(args.citation, cites, prov), indent=2))
    else:
        ap.error("give a citation or --text")
