#!/usr/bin/env python3
"""
redact.py — deterministic, code-based name redaction that runs BEFORE anything leaves the machine.

The interview captures the REAL name (John Doe), derives a code (JoDo = first 2 of first + first 2
of last), and keeps the real string in a LOCAL map. Because the tool knows the real string, it can
find-and-replace every occurrence — including a name buried in a 200-page document — with the code.
The real-name<->code map never leaves the machine; the model only ever sees the code.

Two pieces:
  • Redactor — holds {real -> code} and scrubs text (longest match first, case-insensitive, whole
    word). One-way by design: codes ARE the attorney's pseudonyms, recognizable to them, opaque to
    the model — so there is nothing to un-redact.
  • scan_candidates — a narrow LOCAL heuristic that catches names you DIDN'T declare (honorifics,
    'X v. Y' captions, signature blocks) so you can label them before the send. Suggest-only.
"""
from __future__ import annotations

import re

# Caption parties / name-pairs that are NOT client names — don't flag these.
_WHITELIST = {
    "Commissioner", "United States", "Internal Revenue", "Treasury", "Petitioner", "Respondent",
    "Tax Court", "Supreme Court", "Capital Account", "Qualified Income", "Service",
}


def derive_code(full_name: str) -> str:
    """John Doe -> JoDo (first 2 of first + first 2 of last)."""
    parts = [p for p in re.split(r"[^A-Za-z]+", full_name) if p]
    if len(parts) >= 2:
        return parts[0][:2].capitalize() + parts[-1][:2].capitalize()
    return parts[0][:4].capitalize() if parts else "XX"


def looks_like_name(s: str) -> bool:
    """Heuristic: a multi-word capitalized string is a real name; a single token is already a code."""
    s = s.strip()
    return bool(re.match(r"[A-Z][a-zA-Z'.\-]*(\s+[A-Z][a-zA-Z'.\-]*)+$", s))


class Redactor:
    def __init__(self):
        self._map = {}                 # real string -> code

    def add_name(self, full_name: str, code: str | None = None) -> str:
        """Register a real name (and its surname + first name) -> code. Returns the code."""
        full = full_name.strip()
        code = code or derive_code(full)
        parts = [p for p in re.split(r"\s+", full) if p]
        for t in {full, *([parts[0], parts[-1]] if len(parts) >= 2 else [])}:
            if len(t) >= 2:
                self._map[t] = code
        return code

    def add(self, real: str, code: str) -> str:
        return self.add_name(real, code)

    def redact(self, text: str) -> str:
        for real in sorted(self._map, key=len, reverse=True):   # longest first (full name before parts)
            text = re.sub(r"\b" + re.escape(real) + r"\b", self._map[real], text, flags=re.I)
        return text

    @property
    def names(self) -> list:
        return sorted(self._map)

    @property
    def codes(self) -> list:
        return sorted(set(self._map.values()))


# ---- candidate-name scan (catches UN-declared names at ingest, before send) -------------------
_HONORIFIC = re.compile(
    r"\b(?:Mr|Mrs|Ms|Dr|Prof|Hon|Judge|Justice|Officer|Det|Sgt|Capt|Lt|Rev|Atty)\.?\s+"
    r"([A-Z][a-zA-Z'.\-]+(?:\s+[A-Z][a-zA-Z'.\-]+)?)")
_CAPTION = re.compile(r"\b([A-Z][a-zA-Z'.\-]+)\s+v\.?\s+([A-Z][a-zA-Z'.\-]+)")
_SIGBLOCK = re.compile(
    r"(?:^|\n)\s*(?:By|Name|Signed|Signature|/s/)\s*:?\s*"
    r"([A-Z][a-zA-Z'.\-]+(?:\s+[A-Z][a-zA-Z'.\-]+){0,2})", re.M)
# A capitalized pair is flagged as a possible name UNLESS either word is a legal/structural term.
# This trades precision for recall on purpose: a false flag is dismissed; a leaked name can't be un-sent.
_NAMEPAIR = re.compile(r"\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b")
_LEGAL_WORDS = {
    "Capital", "Account", "Accounts", "Qualified", "Income", "Internal", "Revenue", "Tax", "Court",
    "Treasury", "Economic", "Effect", "Deficit", "Restoration", "Offset", "Partnership", "Agreement",
    "Operating", "Limited", "Service", "Managing", "General", "Partner", "Partners", "Subchapter",
    "Code", "Regulation", "Reg", "Section", "Allocation", "Distribution", "Contribution", "Liability",
    "Basis", "Department", "United", "States", "Supreme", "Substantial", "Special", "Federal", "Form",
    "Schedule", "Exhibit", "Article", "Section", "Notice", "Proc", "Rul", "The", "This", "Under",
    # honorifics / signature words (already caught by the anchored patterns)
    "Mr", "Mrs", "Ms", "Dr", "Prof", "Hon", "Judge", "Justice", "Officer", "Det", "Sgt", "Capt",
    "Lt", "Rev", "Atty", "By", "Name", "Signed", "Signature",
}


def scan_candidates(text: str, redactor: Redactor | None = None, whitelist=None) -> list:
    """Return likely client names present in `text` that are NOT already in the redactor map. Narrow
    and high-precision (honorifics / captions / signature blocks) — it SUGGESTS, the attorney decides."""
    wl = set(whitelist or _WHITELIST)
    known = set()
    if redactor:
        known = {n.lower() for n in redactor.names} | {c.lower() for c in redactor.codes}
    found, seen = [], set()

    def add(name: str):
        n = name.strip(" .,")
        if n and n not in wl and n.lower() not in seen and n.lower() not in known:
            seen.add(n.lower())
            found.append(n)

    for m in _HONORIFIC.finditer(text):
        add(m.group(1))
    for m in _CAPTION.finditer(text):
        add(m.group(1)), add(m.group(2))
    for m in _SIGBLOCK.finditer(text):
        add(m.group(1))
    for m in _NAMEPAIR.finditer(text):
        w1, w2 = m.group(1), m.group(2)
        if w1 not in _LEGAL_WORDS and w2 not in _LEGAL_WORDS:
            add(f"{w1} {w2}")
    return found


if __name__ == "__main__":
    r = Redactor()
    print("  John Doe ->", r.add_name("John Doe"))      # JoDo
    print("  redacted:", r.redact("The agreement names John Doe and Doe as partners; cf. Mr. Roe."))
    print("  candidates:", scan_candidates("By: Jane Q. Public\nSee Smith v. Jones; Officer Brown testified.", r))
