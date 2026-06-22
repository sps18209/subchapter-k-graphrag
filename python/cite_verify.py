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
import urllib.error
import urllib.parse
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
    live = provider.check(c, kind) if provider is not None else None  # None when offline
    if c in corpus_cites:
        out = {"citation": c, "kind": kind, "status": "in_corpus",
               "note": "present in the attorney-curated graph"}
        if live:
            out["live"] = live  # cross-check the curated entry against the live primary source
            if live.get("status") == "not_found":
                out["note"] = (f"in corpus BUT not found at {live.get('source', 'the source')} "
                               "— possible corpus drift; re-verify")
        return out
    if live:
        return {"citation": c, "kind": kind, **live}
    if kind != "unknown":
        return {"citation": c, "kind": kind, "status": "well_formed",
                "note": "valid format, not in corpus — verify against primary source"}
    return {"citation": c, "kind": "unknown", "status": "unrecognized",
            "note": "matches no known citation format — possible error"}


def verify_text(text: str, corpus_cites: set, provider=None) -> list[dict]:
    return [verify(c, corpus_cites, provider) for c in extract_citations(text)]


class OnlineVerifier:
    """Verify a citation against the AUTHORITATIVE primary source for its type:
      regulation       -> eCFR (ecfr.gov, official, reports an 'up to date as of' date)
      statute (IRC)    -> US Code (Cornell LII)
      federal_register -> federalregister.gov
      case             -> CourtListener (needs a free COURTLISTENER_TOKEN)
    .check(citation, kind) returns a verdict dict (status/source/url/...) or None when no
    online source applies (e.g. IRS rulings have no clean API). Network failures -> None,
    so the offline structural check still stands. All lookups are read-only existence checks.
    """
    name = "online"

    def __init__(self, courtlistener_token: str | None = None, timeout: int = 8):
        self.cl_token = courtlistener_token or os.environ.get("COURTLISTENER_TOKEN")
        self.timeout = timeout
        self._ecfr_date = None

    def check(self, citation: str, kind: str):
        try:
            if kind == "regulation":
                return self._ecfr(citation)
            if kind == "statute":
                return self._uscode(citation)
            if kind == "federal_register":
                return self._fedreg(citation)
            if kind == "case":
                return self._courtlistener(citation)
        except Exception:
            return None
        return None

    # -- helpers --
    def _status(self, url: str) -> int:
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:
            return 0

    def _json(self, url: str):
        with urllib.request.urlopen(url, timeout=self.timeout) as r:
            return json.loads(r.read())

    # -- per-source checks --
    def _ecfr_asof(self) -> str:
        if self._ecfr_date is None:
            try:
                d = self._json("https://www.ecfr.gov/api/versioner/v1/titles.json")
                t = next(x for x in d["titles"] if x["number"] == 26)
                self._ecfr_date = t.get("up_to_date_as_of") or t.get("latest_amended_on")
            except Exception:
                self._ecfr_date = "2025-01-01"
        return self._ecfr_date

    def _ecfr(self, citation: str):
        m = re.search(r"\d+\.[\dA-Za-z.\-]+", citation)   # 1.704-2, 1.6011-18, 1.56A-5
        if not m:
            return None
        section = m.group(0)
        part = section.split(".")[0]
        date = self._ecfr_asof()
        url = (f"https://www.ecfr.gov/api/versioner/v1/full/{date}/title-26.xml"
               f"?part={part}&section={section}")
        ok = self._status(url) == 200
        return {"status": "verified_external" if ok else "not_found", "source": "eCFR",
                "as_of": date, "url": f"https://www.ecfr.gov/current/title-26/section-{section}"}

    def _uscode(self, citation: str):
        m = re.search(r"\d+", citation)   # IRC 704(d) -> 704
        if not m:
            return None
        section = m.group(0)
        url = f"https://www.law.cornell.edu/uscode/text/26/{section}"
        ok = self._status(url) == 200
        return {"status": "verified_external" if ok else "not_found",
                "source": "US Code (Cornell LII)", "url": url}

    def _fedreg(self, citation: str):
        url = ("https://www.federalregister.gov/api/v1/documents.json?per_page=1"
               "&conditions%5Bterm%5D=" + urllib.parse.quote(citation))
        d = self._json(url)
        if d.get("count"):
            return {"status": "verified_external", "source": "Federal Register",
                    "url": (d.get("results") or [{}])[0].get("html_url", "")}
        return {"status": "not_found", "source": "Federal Register"}

    def _courtlistener(self, citation: str):
        if not self.cl_token:
            return {"status": "needs_token", "source": "courtlistener",
                    "note": "set COURTLISTENER_TOKEN (free at courtlistener.com) to verify case cites"}
        body = json.dumps({"text": citation}).encode("utf-8")
        req = urllib.request.Request(
            "https://www.courtlistener.com/api/rest/v4/citation-lookup/", data=body,
            headers={"Content-Type": "application/json", "Authorization": "Token " + self.cl_token})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read())
        ok = isinstance(data, list) and any(item.get("clusters") for item in data)
        return {"status": "verified_external" if ok else "not_found", "source": "courtlistener"}


def get_verifier(provider: str | None = None):
    provider = provider if provider is not None else os.environ.get("SUBK_CITE_PROVIDER")
    if not provider or provider == "none":
        return None
    if provider in ("online", "courtlistener"):   # 'courtlistener' kept as an alias
        return OnlineVerifier()
    raise ValueError(f"unknown SUBK_CITE_PROVIDER: {provider!r} (use none|online)")


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
