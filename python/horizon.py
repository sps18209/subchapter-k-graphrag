#!/usr/bin/env python3
"""
horizon.py — a scan of PROPOSED federal tax legislation. NOT authority.

This module is deliberately SEPARATE from the authority graph and the currency gate. Bills
in Congress are *not law* and *not citable authority*; nothing here ever enters the graph,
retrieval, or the currency report. It exists only to surface what MIGHT change partnership
tax — clearly labeled as in-process — so the attorney can watch the horizon.

Source: GPO govinfo BILLS collection via its search API. Works with the shared `DEMO_KEY`
(rate-limited); set GOVINFO_API_KEY (free at api.data.gov) for higher limits. Each hit links
to the official Congress.gov bill page and the govinfo bill PDF.

    python horizon.py                      # default partnership-tax scan, current Congress
    python horizon.py "carried interest"   # custom search terms
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import date

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
SEARCH_URL = "https://api.govinfo.gov/search"

DISCLAIMER = ("PROPOSED / IN-PROCESS federal legislation — NOT law, NOT authority. "
              "A bill is not citable and may never be enacted; verify status before relying.")

# Partnership / Subchapter K focused terms (full-text, within the BILLS collection).
DEFAULT_TERMS = ['"subchapter K"', '"partnership tax"', '"partnership interest"',
                 '"carried interest"', '"partnership audit"']

_TYPE_PATH = {
    "hr": "house-bill", "s": "senate-bill", "hres": "house-resolution", "sres": "senate-resolution",
    "hjres": "house-joint-resolution", "sjres": "senate-joint-resolution",
    "hconres": "house-concurrent-resolution", "sconres": "senate-concurrent-resolution",
}
_TYPE_LABEL = {"hr": "H.R.", "s": "S.", "hres": "H.Res.", "sres": "S.Res.", "hjres": "H.J.Res.",
               "sjres": "S.J.Res.", "hconres": "H.Con.Res.", "sconres": "S.Con.Res."}
# Bill-version suffix -> human legislative stage (so we can show "where is it" with no extra call).
_STAGE = {
    "ih": "introduced (House)", "is": "introduced (Senate)", "rh": "reported (House)",
    "rs": "reported (Senate)", "eh": "passed House", "es": "passed Senate",
    "rfs": "referred to Senate", "rfh": "referred to House", "pcs": "on calendar (Senate)",
    "pch": "on calendar (House)", "enr": "enrolled — passed both chambers", "eas": "engrossed amendment",
}


def current_congress(year: int | None = None) -> int:
    """The Nth Congress for a given year (1st = 1789-90); keeps the default from going stale."""
    year = year or date.today().year
    return (year - 1789) // 2 + 1


def _parse_package(pkg: str) -> dict | None:
    """BILLS-119s4330is -> {congress, type, number, version}."""
    m = re.match(r"BILLS-(\d+)([a-z]+?)(\d+)([a-z]+)$", pkg, re.I)
    if not m:
        return None
    cong, btype, num, ver = m.groups()
    return {"congress": cong, "type": btype.lower(), "number": num, "version": ver.lower()}


def _render_hit(result: dict) -> dict | None:
    pkg = result.get("packageId", "")
    info = _parse_package(pkg)
    if not info:
        return None
    btype, num = info["type"], info["number"]
    path = _TYPE_PATH.get(btype)
    return {
        "bill": f"{_TYPE_LABEL.get(btype, btype.upper())} {num}",
        "title": result.get("title", "").strip(),
        "date": result.get("dateIssued", ""),
        "stage": _STAGE.get(info["version"], info["version"]),
        "url": f"https://www.congress.gov/bill/{info['congress']}th-congress/{path}/{num}" if path else "",
        "pdf": f"https://www.govinfo.gov/content/pkg/{pkg}/pdf/{pkg}.pdf",
        "key": (btype, num),
    }


def scan(terms: list[str] | None = None, congress: int | None = None,
         limit: int = 10, key: str | None = None) -> dict:
    """Return proposed bills matching `terms` in the given Congress (deduped by bill). Network
    failures raise; callers should handle. This NEVER touches the graph — it returns plain data."""
    key = key or os.environ.get("GOVINFO_API_KEY") or "DEMO_KEY"
    congress = congress or current_congress()
    query = " OR ".join(terms or DEFAULT_TERMS)
    body = json.dumps({
        "query": f"collection:BILLS AND congress:{congress} AND ({query})",
        "pageSize": max(limit * 3, 10), "offsetMark": "*",
        "sorts": [{"field": "publishdate", "sortOrder": "DESC"}],
    }).encode()
    req = urllib.request.Request(SEARCH_URL + "?api_key=" + key, data=body,
                                 headers={"Content-Type": "application/json", "User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
    bills, seen = [], set()
    for result in data.get("results", []):
        hit = _render_hit(result)
        if not hit or hit["key"] in seen:   # collapse multiple printings of the same bill
            continue
        seen.add(hit["key"])
        hit.pop("key")
        bills.append(hit)
        if len(bills) >= limit:
            break
    return {"count": data.get("count", 0), "shown": len(bills), "congress": congress, "bills": bills}


def format_scan(s: dict, terms: list[str] | None = None) -> str:
    head = (f"PROPOSED FEDERAL TAX LEGISLATION — {s['congress']}th Congress "
            f"({s['shown']} of {s['count']} matches shown)")
    lines = [head, "*** " + DISCLAIMER + " ***", ""]
    if not s["bills"]:
        lines.append("  (no matching bills found)")
    for b in s["bills"]:
        lines.append(f"  {b['bill']:<11} {b['date']}  {b['title']}")
        meta = f"             stage: {b['stage']}"
        lines.append(meta)
        if b["url"]:
            lines.append(f"             {b['url']}")
    return "\n".join(lines)


if __name__ == "__main__":
    terms = None
    if len(sys.argv) > 1:
        terms = ['"' + " ".join(sys.argv[1:]) + '"']
    try:
        print(format_scan(scan(terms=terms), terms))
    except Exception as e:
        sys.exit(f"horizon scan failed (network / API): {e}")
