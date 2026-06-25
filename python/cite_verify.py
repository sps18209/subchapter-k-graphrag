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
    r"|(?:Prop\.?\s*)?Treas\.?\s*Reg\.?\s*\d[\dA-Za-z.\-]*(?:\([^)]+\))*"   # 1.704-2, 1.6011-18, 1.56A-5
    r"|\d+\s*CFR\s*\d[\dA-Za-z.\-]*(?:\([^)]+\))*"
    r"|Rev\.?\s*Rul\.?\s*\d{2,4}-\d+"
    r"|Rev\.?\s*Proc\.?\s*\d{2,4}-\d+"
    r"|Notice\s*\d{2,4}-\d+"
    r"|Announcement\s*\d{2,4}-\d+"
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


_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"  # gov sites reject the default urllib UA


class OnlineVerifier:
    """Verify a citation against the AUTHORITATIVE primary source for its type:
      regulation       -> eCFR (ecfr.gov, official, reports an 'up to date as of' date)
      statute (IRC)    -> US Code (Cornell LII)
      federal_register -> federalregister.gov
      ruling           -> IRS drop folder (Rev. Rul. / Rev. Proc. / Notice / Announcement PDFs)
      case             -> CourtListener (needs a free COURTLISTENER_TOKEN)
    .check(citation, kind) returns a verdict dict (status/source/url/...) or None when no
    online source applies. Network failures -> None, so the offline structural check still
    stands. All lookups are read-only existence checks.
    """
    name = "online"

    def __init__(self, courtlistener_token: str | None = None, timeout: int = 8):
        self.cl_token = courtlistener_token or os.environ.get("COURTLISTENER_TOKEN")
        self.timeout = timeout
        self._ecfr_date = None

    def check(self, citation: str, kind: str):
        try:
            if kind == "regulation":
                if re.search(r"\bProp\.|REG-\d", citation, re.I):   # proposed regs live in the FR, not eCFR
                    m = re.search(r"REG-\d+-\d+", citation, re.I)
                    return self._fedreg(m.group(0) if m else citation)
                return self._ecfr(citation)
            if kind == "statute":
                return self._uscode(citation)
            if kind == "federal_register":
                return self._fedreg(citation)
            if kind == "ruling":               # Rev. Rul. / Rev. Proc. / Notice / Announcement
                return self._irs_drop(citation)
            if kind == "case":
                return self._courtlistener(citation)
        except Exception:
            return None
        return None

    # -- helpers --
    def _status(self, url: str) -> int:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:
            return 0

    def _json(self, url: str):
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
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
        out = {"status": "verified_external" if ok else "not_found", "source": "eCFR",
               "as_of": date, "url": f"https://www.ecfr.gov/current/title-26/section-{section}"}
        if ok:
            last, n = self._ecfr_amended(part, section)
            if last:
                out["last_amended"] = last
                out["revisions"] = n
        return out

    def _ecfr_amended(self, part: str, section: str):
        """Most-recent amendment date + revision count for a CFR section (eCFR tracks since ~2017)."""
        try:
            d = self._json("https://www.ecfr.gov/api/versioner/v1/versions/title-26.json"
                           f"?part={part}&section={section}")
            dates = sorted({v["date"] for v in d.get("content_versions", [])})
            if dates:
                return dates[-1], len(dates)
        except Exception:
            pass
        return None, 0

    def text(self, citation: str, kind: str | None = None):
        """Fetch the CURRENT primary text of an authority (regs, via eCFR) or an authoritative
        link (statutes -> US Code, rulings -> IRS PDF). Returns {source,url,text,as_of?,
        last_amended?} or None. 'text' is '' when the source isn't cleanly extractable here."""
        kind = kind or classify(citation)
        try:
            if kind == "regulation":
                m = re.search(r"\d+\.[\dA-Za-z.\-]+", citation)
                if not m:
                    return None
                section = m.group(0)
                part = section.split(".")[0]
                date = self._ecfr_asof()
                api = (f"https://www.ecfr.gov/api/versioner/v1/full/{date}/title-26.xml"
                       f"?part={part}&section={section}")
                req = urllib.request.Request(api, headers={"User-Agent": _UA})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    raw = r.read().decode("utf-8", "replace")
                txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)).strip()
                last, _ = self._ecfr_amended(part, section)
                return {"source": "eCFR", "as_of": date, "last_amended": last, "text": txt,
                        "url": f"https://www.ecfr.gov/current/title-26/section-{section}"}
            if kind == "statute":
                m = re.search(r"\d+", citation)
                sec = m.group(0) if m else ""
                url = f"https://www.law.cornell.edu/uscode/text/26/{sec}"
                body = self._uscode_text(sec)
                return {"source": "US Code (Cornell LII)", "url": url,
                        "text": body if len(body) >= 40 else ""}
            if kind == "ruling":
                hit = self._irs_drop(citation)
                if hit:
                    return {"source": hit["source"], "text": "", "url": hit.get("url", "")}
        except Exception:
            return None
        return None

    def _uscode(self, citation: str):
        m = re.search(r"\d+", citation)   # IRC 704(d) -> 704
        if not m:
            return None
        section = m.group(0)
        url = f"https://www.law.cornell.edu/uscode/text/26/{section}"
        ok = self._status(url) == 200
        return {"status": "verified_external" if ok else "not_found",
                "source": "US Code (Cornell LII)", "url": url}

    def _uscode_text(self, section: str) -> str:
        """Best-effort extraction of the section's statutory text from Cornell LII. Reliably
        returns the clean opening language (long sections truncate at the first block) or ''."""
        try:
            req = urllib.request.Request(f"https://www.law.cornell.edu/uscode/text/26/{section}",
                                         headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                html = r.read().decode("utf-8", "replace")
            m = re.search(r"tab-pane[^>]*>(.*?)</div>\s*</div>", html, re.S)
            seg = m.group(1) if m else ""
            return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", seg)).strip()
        except Exception:
            return ""

    def _fedreg(self, citation: str):
        url = ("https://www.federalregister.gov/api/v1/documents.json?per_page=1"
               "&conditions%5Bterm%5D=" + urllib.parse.quote(citation))
        d = self._json(url)
        if d.get("count"):
            return {"status": "verified_external", "source": "Federal Register",
                    "url": (d.get("results") or [{}])[0].get("html_url", "")}
        return {"status": "not_found", "source": "Federal Register"}

    # IRS guidance (Rev. Rul. / Rev. Proc. / Notice / Announcement) publishes as a PDF in the
    # irs.gov "drop" folder with a predictable name, e.g. Rev. Rul. 2024-14 -> rr-24-14.pdf,
    # Notice 2026-7 -> n-26-07.pdf. The drop folder holds recent guidance; older items (pre-2000s)
    # live in the IRB archive and 404 here, so a 404 is "not in the recent folder", not "fake".
    _IRS_PREFIX = (("revrul", "rr"), ("revproc", "rp"), ("notice", "n"), ("announcement", "a"), ("ann", "a"))

    def _irs_drop(self, citation: str):
        m = re.search(r"(rev\.?\s*rul\.?|rev\.?\s*proc\.?|notice|announcement|ann\.?)\s*(\d{2,4})-0*(\d+)",
                      citation, re.I)
        if not m:
            return None
        key = re.sub(r"[.\s]", "", m.group(1)).lower()
        prefix = next((p for k, p in self._IRS_PREFIX if key.startswith(k)), None)
        if not prefix:
            return None
        year, raw = m.group(2)[-2:], str(int(m.group(3)))
        url = ""
        for num in dict.fromkeys((raw, raw.zfill(2))):   # IRS uses both rr-99-6 (old) and n-26-07 (recent)
            url = f"https://www.irs.gov/pub/irs-drop/{prefix}-{year}-{num}.pdf"
            if self._status(url) == 200:
                return {"status": "verified_external", "source": "IRS (irs.gov)", "url": url}
        return {"status": "not_found", "source": "IRS (irs.gov)", "url": url,
                "note": "not in the IRS recent-guidance folder; older rulings are in the IRB "
                        "archive — verify manually"}

    def _courtlistener(self, citation: str):
        if not self.cl_token:
            return {"status": "needs_token", "source": "courtlistener",
                    "note": "set COURTLISTENER_TOKEN (free at courtlistener.com) to verify case cites"}
        hdr = {"Authorization": "Token " + self.cl_token}
        # 1) citation-lookup resolves a reporter cite ("461 U.S. 300") if one is present.
        try:
            req = urllib.request.Request(
                "https://www.courtlistener.com/api/rest/v4/citation-lookup/",
                data=json.dumps({"text": citation}).encode("utf-8"),
                headers={**hdr, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read())
            if isinstance(data, list) and any(item.get("clusters") for item in data):
                return {"status": "verified_external", "source": "courtlistener"}
        except Exception:
            pass
        # 2) fall back to name search — corpus cites are party names ("Commissioner v. Tufts"),
        #    which citation-lookup can't resolve. Confirm the distinctive party appears in the top hit.
        req = urllib.request.Request(
            "https://www.courtlistener.com/api/rest/v4/search/?type=o&q=" + urllib.parse.quote(citation),
            headers=hdr)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.loads(r.read())
        results = data.get("results") or []
        if results:
            top = (results[0].get("caseName") or "").lower()
            parties = [p for p in re.split(r"\bv\.?\s+", citation, flags=re.I) if "commissioner" not in p.lower()]
            words = re.findall(r"[A-Za-z]{3,}", parties[0]) if parties else []
            key = words[0].lower() if words else ""
            if key and key in top:
                url = results[0].get("absolute_url", "")
                if url.startswith("/"):
                    url = "https://www.courtlistener.com" + url
                return {"status": "verified_external", "source": "courtlistener", "url": url}
        return {"status": "not_found", "source": "courtlistener"}


def get_verifier(provider: str | None = None):
    provider = provider if provider is not None else os.environ.get("SUBK_CITE_PROVIDER")
    if not provider or provider == "none":
        return None
    if provider in ("online", "courtlistener"):   # 'courtlistener' kept as an alias
        return OnlineVerifier()
    raise ValueError(f"unknown SUBK_CITE_PROVIDER: {provider!r} (use none|online)")


def corpus_cites(con) -> set:
    return {r[0] for r in con.execute("SELECT citation FROM node")}


def audit_corpus(con, verifier=None) -> list[dict]:
    """Sweep every citation in the corpus against the live primary sources. Each node's citation
    field may be a single cite, a compound, or a concept/term label; we check each real cite once.
    Returns one record per distinct cite: {citation, kind, status, source, url}."""
    verifier = verifier or OnlineVerifier()
    out, seen = [], set()
    for raw in sorted(corpus_cites(con)):
        cites = [raw] if classify(raw) != "unknown" else extract_citations(raw)
        if not cites:
            continue  # concept/term node with no embedded citation — nothing to verify
        for c in cites:
            if c in seen:
                continue
            seen.add(c)
            kind = classify(c)
            try:
                hit = verifier.check(c, kind)
            except Exception:
                hit = None
            rec = {"citation": c, "kind": kind, "status": "unchecked", "source": "", "url": ""}
            if hit:
                rec.update(status=hit.get("status", "unchecked"),
                           source=hit.get("source", ""), url=hit.get("url", ""))
            out.append(rec)
    return out


def flag_reason(citation: str) -> tuple[str, bool]:
    """Why a corpus cite didn't confirm at the live source, and whether it's worth REVIEW (True)
    vs an expected tool limitation (False: proposed regs aren't in eCFR; pre-2010 IRS guidance
    isn't in the recent drop folder)."""
    if "Prop." in citation or "REG-" in citation:
        return ("proposed reg — not codified in eCFR (check the Federal Register)", False)
    m = re.search(r"(\d{2,4})-\d+", citation)
    if m:
        y = int(m.group(1))
        year = y if y > 100 else (2000 + y if y < 40 else 1900 + y)
        if year < 2010:
            return (f"pre-2010 ({year}) — likely in the IRB archive, not the recent IRS folder", False)
        return (f"recent ({year}) — NOT found at the live source; CONFIRM the citation", True)
    return ("not found at the live source — verify manually", True)


if __name__ == "__main__":
    import argparse
    import graph
    ap = argparse.ArgumentParser(description="Verify legal citations against the corpus + primary sources")
    ap.add_argument("citation", nargs="?")
    ap.add_argument("--text", help="extract and verify every citation found in this text")
    ap.add_argument("--source", action="store_true",
                    help="fetch the ACTUAL current text of CITATION from its primary source")
    ap.add_argument("--audit", action="store_true",
                    help="sweep EVERY corpus citation against the live primary sources and report")
    args = ap.parse_args()
    con = graph.build(":memory:")
    cites = corpus_cites(con)
    prov = get_verifier()
    if args.audit:
        recs = audit_corpus(con)
        confirmed = [r for r in recs if r["status"] == "verified_external"]
        flagged = [r for r in recs if r["status"] == "not_found"]
        unchecked = [r for r in recs if r["status"] in ("unchecked", "needs_token")]
        review = [(r, fr) for r in flagged for fr in [flag_reason(r["citation"])] if fr[1]]
        expected = [(r, fr) for r in flagged for fr in [flag_reason(r["citation"])] if not fr[1]]
        print(f"CORPUS CITATION AUDIT — {len(recs)} distinct citations vs live primary sources")
        print(f"  confirmed at the source:            {len(confirmed)}")
        print(f"  NEEDS REVIEW (didn't confirm):      {len(review)}")
        print(f"  expected tool limits (old/proposed):{len(expected)}")
        print(f"  unchecked (cases need a token, etc):{len(unchecked)}")
        if review:
            print("\n--- NEEDS REVIEW: recent cites that did NOT confirm at the source ---")
            for r, (why, _) in review:
                print(f"  {r['citation']:<26} {r['kind']:<12} {why}\n      {r['url']}")
        if expected:
            print("\n--- EXPECTED LIMITATION (not errors; verify manually if you wish) ---")
            for r, (why, _) in expected:
                print(f"  {r['citation']:<26} {r['kind']:<12} {why}")
        if unchecked:
            print("\n--- UNCHECKED: no keyless live source for this type ---")
            for r in unchecked:
                print(f"  {r['citation']:<26} {r['kind']:<12} {r['source'] or '—'}")
    elif args.source:
        if not args.citation:
            ap.error("give a CITATION with --source")
        hit = OnlineVerifier().text(args.citation)
        if not hit:
            ap.error(f"no primary source found for {args.citation!r}")
        if hit.get("text") and len(hit["text"]) > 2000:
            hit = {**hit, "text": hit["text"][:2000] + " … [truncated]"}
        print(json.dumps(hit, indent=2))
    elif args.text:
        print(json.dumps(verify_text(args.text, cites, prov), indent=2))
    elif args.citation:
        print(json.dumps(verify(args.citation, cites, prov), indent=2))
    else:
        ap.error("give a citation, --text, or --source")
