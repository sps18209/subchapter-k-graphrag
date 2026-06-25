#!/usr/bin/env python3
"""
subk_intake.py — the ingestion engine. Turns inputs into a verifiable SEE fact-frame and
reports, transparently, what it could and could NOT take in.

Two doors:
  • a matter FOLDER of documents (the real path) — agreement + capital-account statements, etc.
  • pasted/structured FACTS (the light path) — for hypotheticals and study.

Reliability guarantees:
  • READ-ONLY — never modifies or deletes your source files.
  • Degrades gracefully — uses only the extraction backends actually installed; an unreadable
    file is REPORTED (skipped + why), never guessed at.
  • Deterministic provision detection — agreement provisions (DRO, QIO, capital-account
    maintenance, liquidation-per-CA) are found by literal phrase match, and the matched sentence
    becomes the field's verbatim quote — so every detected fact is traceable to its source text.
"""
from __future__ import annotations

import os
import re

import subk_see

# ---- where files come from -------------------------------------------------------------------
# Home dir (not ~/Downloads): macOS blocks Terminal writes to ~/Downloads. Drop documents here.
MATTERS_ROOT = os.path.expanduser("~/subk-matters")
TEXT_EXT = {".txt", ".md"}
RICH_EXT = {".pdf", ".docx"}
SUPPORTED_EXT = TEXT_EXT | RICH_EXT


def slugify(name: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-") or "matter"


def matter_dir(name: str, create: bool = True) -> str:
    d = os.path.join(MATTERS_ROOT, slugify(name))
    if create:
        os.makedirs(d, exist_ok=True)
    return d


# ---- extraction (read-only, only installed backends) -----------------------------------------
def _extract(path: str) -> tuple[str, str, str]:
    """Return (text, backend, status). status is 'ok' or 'skipped: <reason>' — never an exception."""
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in TEXT_EXT:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                return fh.read(), "text", "ok"
        if ext == ".pdf":
            try:
                import pdfplumber
            except ImportError:
                return "", "-", "skipped: install pdfplumber to read PDFs"
            out = []
            with pdfplumber.open(path) as pdf:
                for pg in pdf.pages:
                    out.append(pg.extract_text() or "")
            text = "\n".join(out).strip()
            if len(text) < 40 * max(1, len(out)):
                return text, "pdfplumber", "ok: low text yield (likely scanned — OCR backend not wired)"
            return text, "pdfplumber", "ok"
        if ext == ".docx":
            try:
                import docx
            except ImportError:
                return "", "-", "skipped: install python-docx to read .docx"
            return "\n".join(p.text for p in docx.Document(path).paragraphs), "python-docx", "ok"
        return "", "-", f"skipped: unsupported type {ext or '(none)'}"
    except Exception as e:
        return "", "-", f"skipped: could not read ({type(e).__name__})"


def ingest_folder(path: str) -> dict:
    """Walk a folder READ-ONLY; return combined facts text + a per-file report. Never raises on a
    bad file — it lands in the report as skipped."""
    report, chunks = [], []
    if not os.path.isdir(path):
        return {"facts": "", "report": [], "error": f"no such folder: {path}"}
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fn in sorted(files):
            if fn.startswith("."):
                continue
            fp = os.path.join(root, fn)
            text, backend, status = _extract(fp)
            report.append({"file": os.path.relpath(fp, path), "backend": backend,
                           "chars": len(text), "status": status})
            if text.strip():
                chunks.append(f"## {os.path.relpath(fp, path)}\n<!-- extractor: {backend} -->\n\n{text}\n")
    return {"facts": "\n".join(chunks), "report": report, "error": None}


# ---- scope: is this even a substantial-economic-effect matter? -------------------------------
_SCOPE_SIGNALS = [
    "economic effect", "substantial", "allocat", "capital account", "704(b)", "section 704",
    "special allocation", "deficit restoration", "qualified income offset", "distributive share",
]


def scope_check(text: str) -> dict:
    t = (text or "").lower()
    hits = [s for s in _SCOPE_SIGNALS if s in t]
    return {"in_scope": bool(hits), "doctrine": subk_see.DOCTRINE, "signals": hits,
            "reason": ("matches substantial-economic-effect signals" if hits else
                       "no §704(b)/allocation/economic-effect signals found — out of scope for the "
                       "only doctrine wired so far (substantial economic effect)")}


# ---- deterministic provision detection (phrase match -> verbatim quote) -----------------------
_PROVISION_PATTERNS = {
    "qualified_income_offset": r"qualified income offset",
    "deficit_restoration_obligation": r"(deficit restoration|restore[sd]?\b[^.]{0,40}deficit|"
                                      r"negative capital account[^.]{0,50}restore)",
    "capital_account_maintenance": r"capital account[^.]{0,60}(maintain|in accordance|"
                                   r"1\.704-1\(b\)\(2\)\(iv\)|section 704\(b\))",
    "liquidation_per_positive_ca": r"liquidat[^.]{0,80}capital account",
}


def _sentence_around(text: str, start: int, end: int) -> str:
    a = text.rfind(".", 0, start) + 1
    b = text.find(".", end)
    b = b + 1 if b != -1 else len(text)
    return re.sub(r"\s+", " ", text[a:b]).strip()[:300]


def detect_provisions(text: str, source: str = "facts") -> dict:
    """Fill an SEE fact-frame's provision fields by literal phrase match. Each detected field's
    quote is the actual sentence it was found in (string-verifiable). Fields it can't detect stay
    null — the tool will then report them as missing rather than guess."""
    frame = subk_see.empty_frame()
    for field, pat in _PROVISION_PATTERNS.items():
        m = re.search(pat, text, re.I)
        if m:
            frame["fields"][field] = {"value": True, "quote": _sentence_around(text, m.start(), m.end()),
                                      "source": source}
    if text.strip():
        frame["sources"].append(source)
    return frame


def frame_from_form(form: dict) -> dict:
    """Light path: attorney-supplied dict of field -> value. Quote = the supplied value, source =
    'attorney input'. Unknown keys are ignored; only the closed SEE vocabulary is accepted."""
    frame = subk_see.empty_frame()
    for field in subk_see.FRAME_FIELDS:
        if field in form and form[field] not in (None, ""):
            frame["fields"][field] = {"value": form[field], "quote": str(form[field]),
                                      "source": "attorney input"}
    frame["sources"].append("attorney input")
    return frame
